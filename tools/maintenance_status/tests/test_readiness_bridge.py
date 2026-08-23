"""Tool 2 feeding Tool 1.

The readiness tool's airworthiness predictor consumes a MaintenanceSnapshot.
These tests drive the real readiness service with the real maintenance service
behind it, so the seam between the two tools is exercised rather than assumed.
"""

from datetime import datetime, timedelta, timezone

from tools.flight_readiness.decision_types import CheckResult, OverallDecision
from tools.flight_readiness.request_response_schemas import (
    FlightReadinessRequest,
    Location,
)
from tools.flight_readiness.service import check_flight_readiness
from tools.flight_readiness.tests.fakes import FakeAircraftClient, FakeWeatherSource
from tools.flight_readiness.tests.fixtures import aircraft_responses as ac
from tools.flight_readiness.tests.fixtures import battery_states as bat
from tools.flight_readiness.tests.fixtures import weather_responses as wx
from tools.maintenance_status.readiness_bridge import MaintenanceStatusReader
from tools.maintenance_status.status_types import MaintenanceStatus
from tools.maintenance_status.tests.fakes import FakeMaintenanceClient
from tools.maintenance_status.tests.fixtures import flight_records as fr
from tools.maintenance_status.tests.fixtures import maintenance_records as mr

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)


def reader(flights=fr.FRESHLY_SERVICED, drone=mr.KNOWN_DRONE, **kwargs):
    return MaintenanceStatusReader(
        client=FakeMaintenanceClient(drone, flights, mr.NO_SERVICE_RECORDS, **kwargs)
    )


def readiness_request():
    start = NOW + timedelta(hours=1)
    return FlightReadinessRequest(
        drone="DRONE-001",
        planned_start_time=start,
        planned_end_time=start + timedelta(hours=1),
        location=Location(longitude=103.8010, latitude=1.3010),
        planned_altitude_m=60.0,
        mission_duration_min=25.0,
    )


def run_readiness(maintenance_reader):
    return check_flight_readiness(
        request=readiness_request(),
        aircraft_client=FakeAircraftClient(ac.READY, bat.HEALTHY),
        maintenance_reader=maintenance_reader,
        forecast_source=FakeWeatherSource(wx.CALM),
        now=NOW,
    )


def result_for(response, check_id):
    return next(c.result for c in response.checks if c.check_id == check_id)


# --- the adapter itself -----------------------------------------------------


def test_bridge_produces_a_readiness_snapshot() -> None:
    snapshot = reader().get_maintenance_status(drone_id="DRONE-001")
    assert snapshot.status is MaintenanceStatus.OK
    assert snapshot.hours_since_service is not None
    assert snapshot.service_interval_hours == 200.0
    assert snapshot.hours_source == "computed_from_flight_records"


def test_bridge_carries_absent_dates_through_as_none() -> None:
    snapshot = reader().get_maintenance_status(drone_id="DRONE-001")
    assert snapshot.last_service_date is None
    assert snapshot.next_due_date is None


# --- the seam, end to end ---------------------------------------------------


def test_serviced_airframe_clears_the_readiness_airworthiness_check() -> None:
    response = run_readiness(reader())
    assert result_for(response, "MNT-001") is CheckResult.CLEAR
    assert response.decision is OverallDecision.GO


def test_hours_past_interval_makes_readiness_no_go() -> None:
    # The whole point of the seam: flight hours summed in Tool 2 turn into a
    # refusal in Tool 1 without either tool knowing the other's internals.
    response = run_readiness(reader(flights=fr.PAST_SERVICE_INTERVAL))
    assert result_for(response, "MNT-001") is CheckResult.FAIL
    assert response.decision is OverallDecision.NO_GO


def test_hours_in_warning_band_makes_readiness_go_with_warnings() -> None:
    response = run_readiness(reader(flights=fr.NEAR_SERVICE_INTERVAL))
    assert result_for(response, "MNT-001") is CheckResult.WARNING
    assert response.decision is OverallDecision.GO_WITH_WARNINGS


def test_unknown_model_leaves_airworthiness_unassessed() -> None:
    # No service plan means no verdict, and an airframe that cannot be
    # assessed is not airworthy by default.
    response = run_readiness(reader(drone=mr.UNKNOWN_MODEL_DRONE))
    assert result_for(response, "MNT-001") is CheckResult.UNAVAILABLE
    assert response.decision is OverallDecision.UNKNOWN


def test_fleet_outage_degrades_readiness_to_unknown() -> None:
    response = run_readiness(reader(fleet_unavailable=True))
    assert result_for(response, "MNT-001") is CheckResult.UNAVAILABLE
    assert response.decision is OverallDecision.UNKNOWN


def test_maintenance_failure_does_not_stop_the_other_predictors() -> None:
    # Predictors do not short-circuit: a pilot still sees weather and battery.
    response = run_readiness(reader(fleet_unavailable=True))
    assert result_for(response, "WX-001") is CheckResult.CLEAR
    assert result_for(response, "BAT-001") is CheckResult.CLEAR
