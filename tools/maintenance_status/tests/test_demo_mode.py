"""Demo mode: the seeded fleet, and the guarantee that it is labelled.

The Garuda Aircraft Service authenticates but returns 504 on every data
endpoint, so the Plex half of both tools runs on seeded records. These tests
pin the two things that matter: the fleet produces the outcomes the demo
depends on, and no simulated response can be mistaken for real data.
"""

import warnings

import pytest

from tools import demo_fleet
from tools.flight_readiness.demo_client import DemoAircraftClient
from tools.maintenance_status.client_protocol import (
    DroneNotFoundError,
    MaintenanceClient,
)
from tools.maintenance_status.demo_client import DemoMaintenanceClient
from tools.maintenance_status.request_response_schemas import (
    MaintenanceStatusRequest,
)
from tools.maintenance_status.service import get_drone_maintenance_status
from tools.maintenance_status.status_types import MaintenanceStatus

warnings.filterwarnings("ignore")


def status_for(name: str, now):
    client = DemoMaintenanceClient(now=now)
    return get_drone_maintenance_status(
        request=MaintenanceStatusRequest(drone=name), client=client, now=now
    )


@pytest.fixture
def now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


# --- the fleet reaches every outcome ----------------------------------------


def test_drone_a_is_ok(now) -> None:
    assert status_for("NTU Sim Drone A", now).status is MaintenanceStatus.OK


def test_drone_b_is_due_soon(now) -> None:
    # The whole point of B: hours inside the warning band, calendar not passed.
    response = status_for("NTU Sim Drone B", now)
    assert response.status is MaintenanceStatus.DUE_SOON
    assert 0 < response.next_due_hours <= 20.0


def test_drone_c_is_overdue_on_hours(now) -> None:
    response = status_for("NTU Sim Drone C", now)
    assert response.status is MaintenanceStatus.OVERDUE
    assert response.hours_since_service > response.service_interval_hours


def test_every_outcome_is_reachable(now) -> None:
    statuses = {status_for(d.name, now).status for d in demo_fleet.FLEET}
    assert MaintenanceStatus.OK in statuses
    assert MaintenanceStatus.DUE_SOON in statuses
    assert MaintenanceStatus.OVERDUE in statuses


def test_hours_are_summed_from_seeded_flights(now) -> None:
    response = status_for("NTU Sim Drone B", now)
    assert response.hours_source == "computed_from_flight_records"
    assert response.flights_counted == 274


def test_all_seeded_flights_fall_after_the_last_service(now) -> None:
    # A fixed weekly tempo would push most sorties before the service date,
    # where they are correctly excluded and the demo understates hours.
    client = DemoMaintenanceClient(now=now)
    for drone in demo_fleet.FLEET:
        ref = client.get_drone(drone=drone.name)
        flights = client.get_flight_records(drone=ref)
        assert len(flights) == drone.sorties_since_service
        assert all(f.flown_on.date() >= drone.last_service_date for f in flights)


# --- resolution -------------------------------------------------------------


def test_resolves_by_name_serial_and_id(now) -> None:
    client = DemoMaintenanceClient(now=now)
    first = demo_fleet.FLEET[0]
    for key in (first.name, first.serial_number, first.drone_id):
        assert client.get_drone(drone=key).drone_id == first.drone_id


def test_resolves_a_bare_letter(now) -> None:
    # So "drone A" and "A" both work when spoken at Claude Desktop.
    client = DemoMaintenanceClient(now=now)
    assert client.get_drone(drone="A").name == "NTU Sim Drone A"


def test_unknown_drone_lists_the_options(now) -> None:
    client = DemoMaintenanceClient(now=now)
    with pytest.raises(DroneNotFoundError) as exc:
        client.get_drone(drone="Nonexistent")
    assert "NTU Sim Drone A" in str(exc.value)


def test_demo_clients_satisfy_the_protocols(now) -> None:
    typed: MaintenanceClient = DemoMaintenanceClient(now=now)
    assert typed is not None

    from tools.flight_readiness.client_protocol import AircraftClient

    aircraft: AircraftClient = DemoAircraftClient(now=now)
    assert aircraft is not None


# --- the labelling guarantee ------------------------------------------------


def test_flag_is_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv(demo_fleet.ENV_FLAG, raising=False)
    assert not demo_fleet.demo_mode_enabled()


def test_flag_accepts_the_usual_truthy_spellings(monkeypatch) -> None:
    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(demo_fleet.ENV_FLAG, value)
        assert demo_fleet.demo_mode_enabled()
    for value in ("0", "false", "", "no"):
        monkeypatch.setenv(demo_fleet.ENV_FLAG, value)
        assert not demo_fleet.demo_mode_enabled()


def test_simulated_responses_are_labelled(monkeypatch) -> None:
    # A simulated number must never be presentable as a real one.
    monkeypatch.setenv(demo_fleet.ENV_FLAG, "1")
    import server

    result = server.get_drone_maintenance_status(drone="NTU Sim Drone A")
    assert result["data_source"] == "simulated_fleet"
    assert result["assumptions"][0] == demo_fleet.SIMULATED_NOTICE


def test_live_responses_carry_no_simulation_label(monkeypatch) -> None:
    monkeypatch.delenv(demo_fleet.ENV_FLAG, raising=False)
    import server

    # No credentials needed: the real client fails auth, which is still a
    # real response and must not be tagged as simulated.
    result = server.get_drone_maintenance_status(drone="NTU Sim Drone A")
    assert "data_source" not in result
