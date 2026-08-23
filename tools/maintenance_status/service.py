"""get_drone_maintenance_status — orchestration.

    validate -> resolve drone -> read service records -> sum hours
             -> compare against plan -> return status

Read-only. Reaches Plex only through the injected client, so the whole tool is
testable with fakes.

The honest shape of what this can answer today:

  hours     REAL — summed from Plex flight records
  interval  LOCAL — from specs/service_plans.py, because Plex exposes no
            maintenance endpoint
  service   ABSENT — no endpoint supplies a last service date, so total
  date      accumulated hours stand in for hours-since-service and the
            calendar check does not run

Every one of those substitutions is named in the response's `assumptions`, so
the number can be audited rather than trusted.
"""

from datetime import datetime, timezone

from tools.maintenance_status.client_protocol import (
    DroneNotFoundError,
    FleetDataUnavailableError,
    MaintenanceClient,
    ServiceRecordsUnavailableError,
)
from tools.maintenance_status.hours_calculator import sum_flight_hours
from tools.maintenance_status.input_validation import validate_request
from tools.maintenance_status.request_response_schemas import (
    DroneRef,
    MaintenanceStatusRequest,
    MaintenanceStatusResponse,
    ServiceRecord,
)
from tools.maintenance_status.specs.service_plans import get_service_plan
from tools.maintenance_status.status_rules import derive_status
from tools.maintenance_status.status_types import MaintenanceStatus

NO_MAINTENANCE_ENDPOINT = (
    "Plex exposes no maintenance endpoint, so total accumulated flight hours "
    "are treated as hours since service."
)
LOCAL_SERVICE_PLAN = (
    "Service interval applied from the local service plan table, not from "
    "Plex; not yet confirmed with client."
)
NO_CALENDAR_CHECK = (
    "No service date on record, so the calendar portion of the check was "
    "not run."
)


def get_drone_maintenance_status(
    *,
    request: MaintenanceStatusRequest,
    client: MaintenanceClient,
    now: datetime,
) -> MaintenanceStatusResponse:
    validation = validate_request(request)
    if not validation.is_valid:
        return MaintenanceStatusResponse(
            status=MaintenanceStatus.NEEDS_INFO,
            missing_inputs=validation.errors,
            message="A drone identifier is required.",
            data_checked_at=now,
        )

    try:
        drone = client.get_drone(drone=request.drone)
    except DroneNotFoundError:
        return MaintenanceStatusResponse(
            status=MaintenanceStatus.NEEDS_INFO,
            missing_inputs=(f"Drone {request.drone!r} could not be resolved",),
            message=f"No drone matching {request.drone!r} in the fleet.",
            data_checked_at=now,
        )
    except FleetDataUnavailableError as exc:
        return MaintenanceStatusResponse(
            status=MaintenanceStatus.UNKNOWN,
            message=f"Fleet service unavailable: {exc}",
            data_checked_at=now,
        )

    last_service, service_assumptions, service_failed = _read_service_records(
        client, drone
    )
    if service_failed:
        return MaintenanceStatusResponse(
            status=MaintenanceStatus.UNKNOWN,
            drone_id=drone.drone_id,
            model=drone.model,
            message="Maintenance records could not be read.",
            data_checked_at=now,
        )

    try:
        flights = client.get_flight_records(drone=drone)
    except FleetDataUnavailableError as exc:
        return MaintenanceStatusResponse(
            status=MaintenanceStatus.UNKNOWN,
            drone_id=drone.drone_id,
            model=drone.model,
            message=f"Flight records unavailable: {exc}",
            data_checked_at=now,
        )

    since = last_service.serviced_on if last_service else None
    hours = sum_flight_hours(flights, since=since)

    plan = get_service_plan(drone.model)
    verdict = derive_status(
        hours_since_service=hours.hours,
        plan=plan,
        last_service_date=since,
        today=now.date(),
    )

    assumptions = list(service_assumptions)
    if plan is not None:
        assumptions.append(LOCAL_SERVICE_PLAN)
    if hours.flights_skipped:
        assumptions.append(
            f"{hours.flights_skipped} flight record(s) had no usable duration "
            f"and were not counted, so airframe hours may be understated."
        )

    return MaintenanceStatusResponse(
        status=verdict.status,
        drone_id=drone.drone_id,
        model=drone.model,
        last_service_date=since,
        last_service_type=last_service.service_type if last_service else None,
        hours_since_service=hours.hours,
        service_interval_hours=plan.interval_hours if plan else None,
        next_due_hours=verdict.next_due_hours,
        next_due_date=verdict.next_due_date,
        hours_source=hours.source,
        flights_counted=hours.flights_counted,
        assumptions=tuple(assumptions),
        message=verdict.message,
        data_checked_at=now,
    )


def _read_service_records(
    client: MaintenanceClient, drone: DroneRef
) -> tuple[ServiceRecord | None, list[str], bool]:
    """Latest service record, the assumptions that follow, and a failure flag.

    No endpoint supplies these today, so the expected path is an empty list —
    which is not a failure, just an airframe with no recorded service. A raised
    ServiceRecordsUnavailableError is different and maps to UNKNOWN.
    """
    try:
        records = client.get_service_records(drone=drone)
    except ServiceRecordsUnavailableError:
        return None, [], True

    if not records:
        return None, [NO_MAINTENANCE_ENDPOINT, NO_CALENDAR_CHECK], False

    latest = max(records, key=lambda record: record.serviced_on)
    return latest, [], False
