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
    ServiceRecordsUnavailableError,
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


MAINTENANCE_PAYLOAD = {
    "maintenance": [
        {
            "drone_id": "DRONE-001",
            "service_date": "2026-07-30",
            "service_type": "100h inspection",
            "airframe_hours": 1204.0,
        },
        {
            "drone_id": "DRONE-001",
            "service_date": "2026-02-14",
            "service_type": "basic",
        },
        {"drone_id": "DRONE-002", "service_date": "2026-06-01", "type": "basic"},
    ]
}

PLANS_PAYLOAD = {
    "maintenance_plans": [
        {
            "drone_id": "DRONE-001",
            "name": "Cerana standard",
            "interval_hours": 100,
            "interval_months": 6,
        }
    ]
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(rest_client, "get_drones", lambda *a, **k: DRONES_PAYLOAD)
    monkeypatch.setattr(rest_client, "get_flights", lambda *a, **k: FLIGHTS_PAYLOAD)
    monkeypatch.setattr(
        rest_client, "get_maintenance_records", lambda *a, **k: MAINTENANCE_PAYLOAD
    )
    monkeypatch.setattr(
        rest_client, "get_maintenance_plans", lambda *a, **k: PLANS_PAYLOAD
    )
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


def test_reads_service_records_for_the_right_drone(client) -> None:
    records = client.get_service_records(drone=client.get_drone(drone="Falcon 1"))
    assert len(records) == 2
    assert {r.serviced_on.isoformat() for r in records} == {"2026-07-30", "2026-02-14"}


def test_service_record_fields_are_mapped(client) -> None:
    records = client.get_service_records(drone=client.get_drone(drone="Falcon 1"))
    latest = max(records, key=lambda r: r.serviced_on)
    assert latest.service_type == "100h inspection"
    assert latest.airframe_hours_at_service == pytest.approx(1204.0)


def test_records_for_other_drones_are_excluded(client) -> None:
    records = client.get_service_records(drone=client.get_drone(drone="Falcon 2"))
    assert [r.serviced_on.isoformat() for r in records] == ["2026-06-01"]


def test_records_without_a_date_are_dropped(client, monkeypatch) -> None:
    monkeypatch.setattr(
        rest_client,
        "get_maintenance_records",
        lambda *a, **k: {"maintenance": [{"drone_id": "DRONE-001", "type": "basic"}]},
    )
    assert client.get_service_records(drone=client.get_drone(drone="Falcon 1")) == []


def test_empty_records_are_not_an_error(client, monkeypatch) -> None:
    # An airframe with no logged service is normal, not a failure. The status
    # rules handle it by skipping the calendar check.
    monkeypatch.setattr(rest_client, "get_maintenance_records", lambda *a, **k: {})
    assert client.get_service_records(drone=client.get_drone(drone="Falcon 1")) == []


def test_maintenance_api_error_becomes_service_records_unavailable(
    client, monkeypatch
) -> None:
    def boom(*args, **kwargs):
        raise rest_client.APIError("maintenance down")

    monkeypatch.setattr(rest_client, "get_maintenance_records", boom)
    with pytest.raises(ServiceRecordsUnavailableError):
        client.get_service_records(drone=client.get_drone(drone="Falcon 1"))


# --- service plans ----------------------------------------------------------


def test_reads_the_plex_service_plan(client) -> None:
    plan = client.get_service_plan(drone=client.get_drone(drone="Falcon 1"))
    assert plan is not None
    assert plan.interval_hours == pytest.approx(100.0)
    assert plan.interval_months == 6
    assert plan.source == "plex_maintenance_plan"


def test_no_plan_for_this_drone_returns_none(client) -> None:
    # None lets the service layer fall back to the local specs table rather
    # than treating an absent plan as an absent interval.
    assert client.get_service_plan(drone=client.get_drone(drone="Falcon 2")) is None


def test_plan_without_an_interval_is_ignored(client, monkeypatch) -> None:
    monkeypatch.setattr(
        rest_client,
        "get_maintenance_plans",
        lambda *a, **k: {"maintenance_plans": [{"drone_id": "DRONE-001", "name": "x"}]},
    )
    assert client.get_service_plan(drone=client.get_drone(drone="Falcon 1")) is None
