from datetime import date

import pytest

from tools.maintenance_status.specs.service_plans import (
    ServicePlan,
    get_service_plan,
    warning_band_hours,
)
from tools.maintenance_status.status_rules import derive_status
from tools.maintenance_status.status_types import MaintenanceStatus

PLAN = ServicePlan(model="Matrice 4", interval_hours=200.0, interval_months=6)
TODAY = date(2026, 8, 25)


def verdict(hours, *, plan=PLAN, last_service=None, today=TODAY):
    return derive_status(
        hours_since_service=hours,
        plan=plan,
        last_service_date=last_service,
        today=today,
    )


def test_low_hours_are_ok() -> None:
    result = verdict(42.1)
    assert result.status is MaintenanceStatus.OK
    assert result.next_due_hours == pytest.approx(157.9)


def test_inside_the_warning_band_is_due_soon() -> None:
    # 182.4 h leaves 17.6 h, inside the 20 h band on a 200 h interval.
    assert verdict(182.4).status is MaintenanceStatus.DUE_SOON


def test_just_outside_the_warning_band_is_still_ok() -> None:
    assert verdict(179.0).status is MaintenanceStatus.OK


def test_exactly_at_the_interval_is_overdue() -> None:
    # A boundary that should fail closed: at the interval, service is due.
    assert verdict(200.0).status is MaintenanceStatus.OVERDUE


def test_past_the_interval_is_overdue() -> None:
    result = verdict(214.7)
    assert result.status is MaintenanceStatus.OVERDUE
    assert result.next_due_hours < 0


def test_calendar_date_passed_is_overdue_despite_low_hours() -> None:
    # Serviced Jan 2025, 6 month interval -> due Jul 2025, long past.
    result = verdict(51.0, last_service=date(2025, 1, 10))
    assert result.status is MaintenanceStatus.OVERDUE
    assert result.next_due_date == date(2025, 7, 10)
    assert "has passed" in result.message


def test_calendar_date_upcoming_leaves_status_on_hours() -> None:
    result = verdict(51.0, last_service=date(2026, 7, 30))
    assert result.status is MaintenanceStatus.OK
    assert result.next_due_date == date(2027, 1, 30)


def test_no_service_date_means_no_calendar_check() -> None:
    # The realistic case today: no maintenance endpoint, so no service date.
    # The check that cannot run must not quietly count as passing.
    result = verdict(51.0, last_service=None)
    assert result.next_due_date is None
    assert result.status is MaintenanceStatus.OK


def test_month_rollover_across_a_year_boundary() -> None:
    result = verdict(10.0, last_service=date(2026, 10, 15))
    assert result.next_due_date == date(2027, 4, 15)


def test_month_end_clamps_rather_than_overflowing() -> None:
    # 31 Aug + 6 months has no 31 February equivalent; clamp to month end.
    result = verdict(10.0, last_service=date(2026, 8, 31), today=date(2026, 9, 1))
    assert result.next_due_date == date(2027, 2, 28)


def test_no_plan_is_needs_info() -> None:
    result = verdict(120.0, plan=None)
    assert result.status is MaintenanceStatus.NEEDS_INFO
    assert "No service plan" in result.message


def test_plan_without_an_hours_interval_is_needs_info() -> None:
    plan = ServicePlan(model="Prototype X", interval_hours=None)
    assert verdict(120.0, plan=plan).status is MaintenanceStatus.NEEDS_INFO


def test_unknown_hours_is_unknown_not_ok() -> None:
    assert verdict(None).status is MaintenanceStatus.UNKNOWN


# --- the plan table ---------------------------------------------------------


def test_known_model_has_a_plan() -> None:
    plan = get_service_plan("Matrice 4")
    assert plan is not None and plan.interval_hours == 200.0


def test_lookup_is_case_and_whitespace_tolerant() -> None:
    assert get_service_plan("  matrice 4  ") is not None


def test_unknown_model_has_no_plan() -> None:
    assert get_service_plan("Prototype X") is None
    assert get_service_plan(None) is None
    assert get_service_plan("   ") is None


def test_warning_band_scales_with_the_interval() -> None:
    assert warning_band_hours(200.0) == pytest.approx(20.0)
    assert warning_band_hours(150.0) == pytest.approx(15.0)
