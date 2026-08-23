"""Maintenance snapshots for the airworthiness predictor.

These stand in for Tool 2's output. Calibrated to a 200 hour / 6 month service
interval, which is itself an unconfirmed industry benchmark.
"""

from datetime import date, datetime, timedelta, timezone

from tools.flight_readiness.request_response_schemas import MaintenanceSnapshot
from tools.maintenance_status.status_types import MaintenanceStatus

SG_TIMEZONE = timezone(timedelta(hours=8))

CHECKED_AT = datetime(2026, 8, 25, 8, 45, tzinfo=SG_TIMEZONE)


FRESHLY_SERVICED = MaintenanceSnapshot(
    status=MaintenanceStatus.OK,
    hours_since_service=42.1,
    service_interval_hours=200.0,
    last_service_date=date(2026, 7, 30),
    next_due_date=date(2027, 1, 30),
    hours_source="plex_aggregate",
    checked_at=CHECKED_AT,
)

NEAR_SERVICE_INTERVAL = MaintenanceSnapshot(
    status=MaintenanceStatus.DUE_SOON,
    hours_since_service=182.4,
    service_interval_hours=200.0,
    last_service_date=date(2026, 3, 2),
    next_due_date=date(2026, 9, 2),
    hours_source="computed_from_flight_records",
    checked_at=CHECKED_AT,
)

OVERDUE_ON_HOURS = MaintenanceSnapshot(
    status=MaintenanceStatus.OVERDUE,
    hours_since_service=214.7,
    service_interval_hours=200.0,
    last_service_date=date(2026, 2, 14),
    next_due_date=date(2026, 8, 14),
    hours_source="computed_from_flight_records",
    checked_at=CHECKED_AT,
)

# Hours are fine; the calendar date has passed. Still OVERDUE.
OVERDUE_ON_CALENDAR = MaintenanceSnapshot(
    status=MaintenanceStatus.OVERDUE,
    hours_since_service=51.0,
    service_interval_hours=200.0,
    last_service_date=date(2026, 1, 10),
    next_due_date=date(2026, 7, 10),
    hours_source="plex_aggregate",
    checked_at=CHECKED_AT,
)

# Drone resolved but has no service plan on record.
NO_SERVICE_PLAN = MaintenanceSnapshot(
    status=MaintenanceStatus.NEEDS_INFO,
    hours_since_service=None,
    service_interval_hours=None,
    last_service_date=None,
    next_due_date=None,
    hours_source=None,
    checked_at=CHECKED_AT,
)

# Fleet Management was unreachable.
SERVICE_UNAVAILABLE = MaintenanceSnapshot(
    status=MaintenanceStatus.UNKNOWN,
    hours_since_service=None,
    service_interval_hours=None,
    last_service_date=None,
    next_due_date=None,
    hours_source=None,
    checked_at=CHECKED_AT,
)

# Older than the 7-day maintenance staleness policy.
STALE_RECORD = MaintenanceSnapshot(
    status=MaintenanceStatus.OK,
    hours_since_service=60.0,
    service_interval_hours=200.0,
    last_service_date=date(2026, 6, 1),
    next_due_date=date(2026, 12, 1),
    hours_source="plex_aggregate",
    checked_at=CHECKED_AT - timedelta(days=12),
)
