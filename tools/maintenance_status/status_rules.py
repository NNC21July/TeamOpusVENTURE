"""Derive a maintenance status from hours, a service plan and a service date.

Kept separate from service.py for the same reason the readiness tool keeps
aggregation separate from orchestration: these are the rules, and they should
be readable and testable without any fetching around them.

Two checks, and either one can produce OVERDUE:

  hours    — hours since service against the plan's interval
  calendar — today against the next-due date derived from the last service

The calendar check only runs when a last service date exists. Plex has no
maintenance endpoint, so in practice it does not run today — and a check that
cannot run must not quietly count as passing.

Pure. `today` is passed in rather than read from the clock.
"""

from dataclasses import dataclass
from datetime import date

from tools.maintenance_status.specs.service_plans import (
    ServicePlan,
    warning_band_hours,
)
from tools.maintenance_status.status_types import MaintenanceStatus


@dataclass(frozen=True)
class StatusVerdict:
    status: MaintenanceStatus
    next_due_hours: float | None = None
    next_due_date: date | None = None
    message: str | None = None


def derive_status(
    *,
    hours_since_service: float | None,
    plan: ServicePlan | None,
    last_service_date: date | None,
    today: date,
) -> StatusVerdict:
    if plan is None or plan.interval_hours is None:
        return StatusVerdict(
            status=MaintenanceStatus.NEEDS_INFO,
            message=(
                "No service plan on record for this airframe, so it cannot be "
                "compared against a service interval."
            ),
        )

    if hours_since_service is None:
        return StatusVerdict(
            status=MaintenanceStatus.UNKNOWN,
            message="Flight hours could not be determined.",
        )

    interval = plan.interval_hours
    remaining = round(interval - hours_since_service, 2)
    next_due_date = _next_due_date(plan, last_service_date)

    # Calendar first: a date that has passed is overdue no matter how few
    # hours the airframe has flown since.
    if next_due_date is not None and today > next_due_date:
        return StatusVerdict(
            status=MaintenanceStatus.OVERDUE,
            next_due_hours=remaining,
            next_due_date=next_due_date,
            message=(
                f"Service was due on {next_due_date.isoformat()}, which has passed."
            ),
        )

    if hours_since_service >= interval:
        return StatusVerdict(
            status=MaintenanceStatus.OVERDUE,
            next_due_hours=remaining,
            next_due_date=next_due_date,
            message=(
                f"Airframe has flown {hours_since_service:.1f} hours against a "
                f"{interval:.0f} hour service interval."
            ),
        )

    if remaining <= warning_band_hours(interval):
        return StatusVerdict(
            status=MaintenanceStatus.DUE_SOON,
            next_due_hours=remaining,
            next_due_date=next_due_date,
            message=(
                f"{remaining:.1f} hours remain before the "
                f"{interval:.0f} hour service interval."
            ),
        )

    return StatusVerdict(
        status=MaintenanceStatus.OK,
        next_due_hours=remaining,
        next_due_date=next_due_date,
        message=(
            f"Airframe is within its service interval, with {remaining:.1f} "
            f"hours remaining."
        ),
    )


def _next_due_date(plan: ServicePlan, last_service_date: date | None) -> date | None:
    """Calendar due date, or None when it cannot be derived.

    Needs both a last service date and a calendar interval. Returning None is
    the honest answer — the alternative would be inventing a service date and
    reporting a due date the operator might act on.
    """
    if last_service_date is None or plan.interval_months is None:
        return None

    month_index = last_service_date.month - 1 + plan.interval_months
    year = last_service_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(last_service_date.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days
