from tools.flight_readiness.decision_types import CheckResult
from tools.flight_readiness.predictors.airworthiness_predictor import (
    check_airworthiness,
)
from tools.flight_readiness.tests.fixtures import aircraft_responses as ac
from tools.flight_readiness.tests.fixtures import maintenance_records as mnt


def maintenance_check(snapshot, aircraft=ac.READY):
    checks = {
        c.check_id: c
        for c in check_airworthiness(aircraft=aircraft, maintenance=snapshot)
    }
    return checks["MNT-001"]


def state_check(aircraft, snapshot=mnt.FRESHLY_SERVICED):
    checks = {
        c.check_id: c
        for c in check_airworthiness(aircraft=aircraft, maintenance=snapshot)
    }
    return checks["MNT-002"]


def test_returns_two_checks() -> None:
    checks = check_airworthiness(aircraft=ac.READY, maintenance=mnt.FRESHLY_SERVICED)
    assert [c.check_id for c in checks] == ["MNT-001", "MNT-002"]


def test_freshly_serviced_is_clear() -> None:
    assert maintenance_check(mnt.FRESHLY_SERVICED).result is CheckResult.CLEAR


def test_due_soon_is_a_warning() -> None:
    assert maintenance_check(mnt.NEAR_SERVICE_INTERVAL).result is CheckResult.WARNING


def test_overdue_on_hours_fails() -> None:
    assert maintenance_check(mnt.OVERDUE_ON_HOURS).result is CheckResult.FAIL


def test_overdue_on_calendar_fails_despite_low_hours() -> None:
    check = maintenance_check(mnt.OVERDUE_ON_CALENDAR)
    assert check.result is CheckResult.FAIL
    assert check.observed["hours_since_service"] < check.threshold["service_interval_hours"]


def test_no_service_plan_is_unavailable_not_clear() -> None:
    # An airframe with no readable service history is not known airworthy.
    assert maintenance_check(mnt.NO_SERVICE_PLAN).result is CheckResult.UNAVAILABLE


def test_fleet_management_unavailable() -> None:
    assert maintenance_check(mnt.SERVICE_UNAVAILABLE).result is CheckResult.UNAVAILABLE


def test_missing_snapshot_is_unavailable() -> None:
    assert maintenance_check(None).result is CheckResult.UNAVAILABLE


def test_ready_to_fly_is_clear() -> None:
    assert state_check(ac.READY).result is CheckResult.CLEAR


def test_init_status_fails() -> None:
    check = state_check(ac.NOT_READY_TO_FLY)
    assert check.result is CheckResult.FAIL
    assert "RTF" in check.message


def test_already_flying_is_a_warning() -> None:
    # A scheduling conflict, not an airworthiness failure.
    assert state_check(ac.ALREADY_FLYING).result is CheckResult.WARNING


def test_checks_carry_observed_and_threshold() -> None:
    for check in check_airworthiness(
        aircraft=ac.READY, maintenance=mnt.NEAR_SERVICE_INTERVAL
    ):
        assert check.observed
        assert check.message
