"""Pilot-supplied battery charge.

Plex stores battery state nowhere — verified against the live sandbox:
/aircraft/batteries and friends return 404 (not 403, so not a permissions
problem), and neither the drone record nor the flight record carries a battery
field. It exists only in live telemetry, which emits only while a drone flies.

So for a pre-flight check the pilot reading the controller is frequently the
only source there is. These tests pin the precedence and the labelling.
"""

from datetime import datetime, timedelta, timezone

import pytest

from tools.flight_readiness.decision_types import CheckResult, OverallDecision
from tools.flight_readiness.request_response_schemas import (
    BatteryRecord,
    FlightReadinessRequest,
    Location,
)
from tools.flight_readiness.service import check_flight_readiness
from tools.flight_readiness.tests.fakes import (
    FakeAircraftClient,
    FakeMaintenanceReader,
    FakeWeatherSource,
)
from tools.flight_readiness.tests.fixtures import aircraft_responses as ac
from tools.flight_readiness.tests.fixtures import battery_states as bat
from tools.flight_readiness.tests.fixtures import maintenance_records as mnt
from tools.flight_readiness.tests.fixtures import weather_responses as wx

NOW = datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc)


def make_request(**overrides):
    defaults = dict(
        drone="DRONE-001",
        planned_start_time=NOW + timedelta(hours=1),
        planned_end_time=NOW + timedelta(hours=2),
        location=Location(longitude=103.8010, latitude=1.3010),
        planned_altitude_m=60.0,
        mission_duration_min=25.0,
    )
    defaults.update(overrides)
    return FlightReadinessRequest(**defaults)


def run(*, battery=bat.HEALTHY, charge=None, aircraft=ac.READY):
    return check_flight_readiness(
        request=make_request(battery_charge_percent=charge),
        aircraft_client=FakeAircraftClient(aircraft, battery),
        maintenance_reader=FakeMaintenanceReader(mnt.FRESHLY_SERVICED),
        forecast_source=FakeWeatherSource(wx.CALM),
        now=NOW,
    )


def result_for(response, check_id):
    return next(c.result for c in response.checks if c.check_id == check_id)


# --- the gap this closes ----------------------------------------------------


def test_without_any_battery_source_endurance_is_unavailable() -> None:
    # The live sandbox's situation: no battery anywhere.
    response = run(battery=None)
    assert result_for(response, "BAT-001") is CheckResult.UNAVAILABLE
    assert response.decision is OverallDecision.UNKNOWN


def test_pilot_charge_makes_endurance_assessable() -> None:
    response = run(battery=None, charge=92)
    assert result_for(response, "BAT-001") is CheckResult.CLEAR
    assert response.decision is OverallDecision.GO


def test_pilot_charge_can_still_produce_a_refusal() -> None:
    # It enables the check; it does not bias it toward approval.
    response = run(battery=None, charge=12)
    assert result_for(response, "BAT-001") is CheckResult.FAIL
    assert response.decision is OverallDecision.NO_GO


# --- precedence -------------------------------------------------------------


def test_system_reading_wins_over_the_pilot() -> None:
    # HEALTHY reports 0.95; the pilot says 20. The system reading is used, so
    # the check still clears.
    response = run(battery=bat.HEALTHY, charge=20)
    assert result_for(response, "BAT-001") is CheckResult.CLEAR
    assert any("system reading was used" in a for a in response.assumptions)


def test_pilot_charge_fills_only_the_missing_field() -> None:
    # Health is known but charge is not: keep the known health, take the
    # pilot's charge. 45 x 0.95 health x 0.90 charge is still ample for 25 min.
    partial = BatteryRecord(state_of_health=0.95, cycle_count=40)
    response = run(battery=partial, charge=90)
    check = next(c for c in response.checks if c.check_id == "BAT-001")
    assert check.observed["state_of_health"] == pytest.approx(0.95)
    assert check.observed["state_of_charge"] == pytest.approx(0.90)


# --- labelling --------------------------------------------------------------


def test_a_pilot_figure_is_always_labelled() -> None:
    # A reported number must never be mistaken for a measured one.
    response = run(battery=None, charge=92)
    assert any("reported by the pilot" in a for a in response.assumptions)


def test_no_label_when_no_pilot_figure_was_given() -> None:
    response = run(battery=bat.HEALTHY)
    assert not any("pilot" in a.lower() for a in response.assumptions)


# --- validation -------------------------------------------------------------


def test_charge_above_one_hundred_is_rejected() -> None:
    response = run(battery=None, charge=150)
    assert response.decision is OverallDecision.NEEDS_INFO
    assert any("between 0 and 100" in e for e in response.missing_inputs)


def test_negative_charge_is_rejected() -> None:
    response = run(battery=None, charge=-5)
    assert response.decision is OverallDecision.NEEDS_INFO


def test_zero_charge_is_valid_input_and_fails_the_check() -> None:
    # 0 is a legitimate reading, not missing data.
    response = run(battery=None, charge=0)
    assert response.decision is OverallDecision.NO_GO
    assert result_for(response, "BAT-001") is CheckResult.FAIL
