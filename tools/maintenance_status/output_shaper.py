"""Shape the maintenance response for the model.

The per-tool trim stage of the governance read path. Fields whose value is
None are dropped — except `hours_source`, which is always emitted, because
whether a number was aggregated by Plex or summed client-side is exactly the
thing a reviewer needs to see and a null there is itself informative.
"""

from datetime import date, datetime

from tools.maintenance_status.request_response_schemas import (
    MaintenanceStatusResponse,
)


def shape_maintenance_status_response(response: MaintenanceStatusResponse) -> dict:
    shaped: dict[str, object] = {"status": response.status.value}

    for key, value in (
        ("drone_id", response.drone_id),
        ("model", response.model),
        ("last_service_date", response.last_service_date),
        ("last_service_type", response.last_service_type),
        ("hours_since_service", response.hours_since_service),
        ("service_interval_hours", response.service_interval_hours),
        ("next_due_hours", response.next_due_hours),
        ("next_due_date", response.next_due_date),
        ("flights_counted", response.flights_counted),
        ("message", response.message),
    ):
        if value is not None:
            shaped[key] = _serialise(value)

    # Always present, even when null: it is the audit trail for the number.
    shaped["hours_source"] = response.hours_source

    for key, values in (
        ("missing_inputs", response.missing_inputs),
        ("assumptions", response.assumptions),
    ):
        if values:
            shaped[key] = list(values)

    if response.data_checked_at is not None:
        shaped["data_checked_at"] = response.data_checked_at.isoformat()

    return shaped


def _serialise(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 2)
    return value
