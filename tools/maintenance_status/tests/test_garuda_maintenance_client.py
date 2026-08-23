"""Client tests against the confirmed Plex payload shapes.

Payloads follow the field names the working MCP server already relies on:

    drones   drone_id, name, serial_number, drone_model_id, status
    flights  flight_id, status, drone.name, date (epoch ms, -1 unset),
             duration {hours, minutes, seconds}

rest_client is monkeypatched, so no network and no credentials are needed.
"""

import pytest

from api_client import rest_client
from tools.maintenance_status.client_protocol import (
    DroneNotFoundError,
    FleetDataUnavailableError,
    MaintenanceClient,
)
from tools.maintenance_status.garuda_maintenance_client import (
    GarudaMaintenanceClient,
)
from tools.maintenance_status.request_response_schemas import DroneRef

DRONES_PAYLOAD = {
    "drones": [
        {
            "drone_id": "DRONE-001",
            "name": "Falcon 1",
            "serial_number": "SN-0001",
            "drone_model_id": "MODEL-M4",
            "drone_model": "Matrice 4",
            "status": "RTF",
        },
        {
            "drone_id": "DRONE-002",
            "name": "Falcon 2",
            "serial_number": "SN-0002",
            "drone_model_id": "MODEL-M4",
            "status": "INIT",
        },
    ]
}

FLIGHTS_PAYLOAD = {
    "flights": [
        {
            "flight_id": "FLT-0001",
            "status": "postflight",
            "drone": {"name": "Falcon 1"},
            "date": 1_787_000_000_000,
            "duration": {"hours": 0, "minutes": 40, "seconds": 0},
        },
        {
            "flight_id": "FLT-0002",
            "status": "postflight",
            "drone": {"name": "Falcon 2"},
            "date": 1_787_100_000_000,
            "duration": {"hours": 1, "minutes": 5, "seconds": 30},
        },
        {
            "flight_id": "FLT-0003",
            "status": "preflight",
            "drone": {"name": "Falcon 1"},
            "date": -1,
            "duration": {"hours": 0, "minutes": 0, "seconds": 0},
        },
    ]
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(rest_client, "get_drones", lambda *a, **k: DRONES_PAYLOAD)
    monkeypatch.setattr(rest_client, "get_flights", lambda *a, **k: FLIGHTS_PAYLOAD)
    return GarudaMaintenanceClient()


def test_satisfies_the_protocol() -> None:
    typed: MaintenanceClient = GarudaMaintenanceClient()
    assert typed is not None


def test_resolves_by_name(client) -> None:
    drone = client.get_drone(drone="Falcon 1")
    assert drone.drone_id == "DRONE-001"
    assert drone.model == "Matrice 4"


def test_resolves_by_serial(client) -> None:
    assert client.get_drone(drone="SN-0002").drone_id == "DRONE-002"


def test_resolves_by_id(client) -> None:
    assert client.get_drone(drone="DRONE-002").name == "Falcon 2"


def test_resolution_is_case_insensitive(client) -> None:
    assert client.get_drone(drone="  falcon 1  ").drone_id == "DRONE-001"


def test_unknown_drone_raises_not_found(client) -> None:
    with pytest.raises(DroneNotFoundError):
        client.get_drone(drone="Falcon 99")


def test_blank_identifier_raises_not_found(client) -> None:
    with pytest.raises(DroneNotFoundError):
        client.get_drone(drone="   ")


def test_model_id_without_a_name_yields_no_model(client) -> None:
    # Falcon 2 has only drone_model_id. Returning None is correct: the service
    # plan table is keyed by name, so this becomes NEEDS_INFO downstream
    # rather than a comparison against an invented interval.
    assert client.get_drone(drone="Falcon 2").model is None


def test_api_error_becomes_fleet_unavailable(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise rest_client.APIError("service down")

    monkeypatch.setattr(rest_client, "get_drones", boom)
    with pytest.raises(FleetDataUnavailableError):
        GarudaMaintenanceClient().get_drone(drone="Falcon 1")


# --- flights ----------------------------------------------------------------


def test_flights_are_filtered_by_drone_name(client) -> None:
    # Flights link to a drone by NAME, not id.
    records = client.get_flight_records(drone=client.get_drone(drone="Falcon 1"))
    assert {r.flight_id for r in records} == {"FLT-0001", "FLT-0003"}


def test_duration_object_is_flattened(client) -> None:
    records = client.get_flight_records(drone=client.get_drone(drone="Falcon 2"))
    assert records[0].duration_seconds == pytest.approx(3930.0)


def test_epoch_date_becomes_aware_datetime(client) -> None:
    records = client.get_flight_records(drone=client.get_drone(drone="Falcon 1"))
    dated = next(r for r in records if r.flight_id == "FLT-0001")
    assert dated.flown_on is not None and dated.flown_on.tzinfo is not None


def test_unset_date_sentinel_becomes_none(client) -> None:
    records = client.get_flight_records(drone=client.get_drone(drone="Falcon 1"))
    undated = next(r for r in records if r.flight_id == "FLT-0003")
    assert undated.flown_on is None


def test_flights_api_error_becomes_fleet_unavailable(client, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise rest_client.APIError("flights down")

    monkeypatch.setattr(rest_client, "get_flights", boom)
    with pytest.raises(FleetDataUnavailableError):
        client.get_flight_records(drone=DroneRef(drone_id="DRONE-001", name="Falcon 1"))


# --- service records --------------------------------------------------------


def test_service_records_are_empty_not_an_error(client) -> None:
    # No Plex service exposes maintenance records. An empty list means "no
    # recorded service", which the status rules handle by skipping the
    # calendar check — it is not a failure.
    records = client.get_service_records(drone=client.get_drone(drone="Falcon 1"))
    assert records == []
