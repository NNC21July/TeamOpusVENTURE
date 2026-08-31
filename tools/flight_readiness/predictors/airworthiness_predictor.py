"""Airworthiness predictor: is this airframe permitted to fly at all?

Two independent questions, so two checks:

  MNT-001  maintenance   — is the airframe within its service interval?
  MNT-002  aircraft state — is the drone actually ready to fly right now?

Pure. Never fetches, never raises. Consumes Tool 2's output via the
MaintenanceSnapshot record rather than calling Tool 2 itself.
"""

from tools.flight_readiness.decision_types import CheckResult
from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    CheckDetail,
    MaintenanceSnapshot,
)
from tools.maintenance_status.status_types import MaintenanceStatus

# Statuses on the DRONE RECORD that mean the airframe is in service.
#
# Verified against the live sandbox: /aircraft/drones reports status "active"
# for every drone. The RTF / INIT vocabulary in the onboarding handbook is the
# LIVE FLIGHT state, which arrives over the telemetry WebSocket, not a field on
# the drone record. Checking a record-level status against "RTF" would fail
# every real drone, so both vocabularies are accepted here.
#
# RTF is kept so that a live-telemetry status still passes once the streaming
# bridge feeds it in.
IN_SERVICE_STATUSES = frozenset({"ACTIVE", "RTF"})

# Explicitly not ready. Anything unrecognised is treated as unavailable rather
# than as a failure, since a status this tool does not know about is not
# evidence that the airframe is grounded.
NOT_READY_STATUSES = frozenset({"INIT", "INACTIVE", "RETIRED", "MAINTENANCE"})


def check_airworthiness(
    *, aircraft: AircraftRecord, maintenance: MaintenanceSnapshot | None
) -> tuple[CheckDetail, ...]:
    return (
        _check_maintenance(maintenance=maintenance),
        _check_aircraft_state(aircraft=aircraft),
    )


def _check_maintenance(*, maintenance: MaintenanceSnapshot | None) -> CheckDetail:
    if maintenance is None:
        return CheckDetail(
            check_id="MNT-001",
            category="airworthiness",
            result=CheckResult.UNAVAILABLE,
            message="Maintenance status could not be retrieved.",
        )

    observed = {
        "maintenance_status": maintenance.status.value,
        "hours_since_service": maintenance.hours_since_service,
        "last_service_date": (
            maintenance.last_service_date.isoformat()
            if maintenance.last_service_date
            else None
        ),
    }
    threshold = {
        "service_interval_hours": maintenance.service_interval_hours,
        "next_due_date": (
            maintenance.next_due_date.isoformat() if maintenance.next_due_date else None
        ),
    }

    # UNKNOWN and NEEDS_INFO both mean "could not assess". Neither is a pass:
    # an airframe whose service history is unreadable is not known airworthy.
    if maintenance.status in (MaintenanceStatus.UNKNOWN, MaintenanceStatus.NEEDS_INFO):
        message = (
            "Fleet Management was unavailable, so service status is unknown."
            if maintenance.status is MaintenanceStatus.UNKNOWN
            else "No service plan on record for this airframe."
        )
        return CheckDetail(
            check_id="MNT-001",
            category="airworthiness",
            result=CheckResult.UNAVAILABLE,
            observed=observed,
            threshold=threshold,
            message=message,
        )

    if maintenance.status is MaintenanceStatus.OVERDUE:
        return CheckDetail(
            check_id="MNT-001",
            category="airworthiness",
            result=CheckResult.FAIL,
            observed=observed,
            threshold=threshold,
            message="Airframe is overdue for service.",
        )

    if maintenance.status is MaintenanceStatus.DUE_SOON:
        return CheckDetail(
            check_id="MNT-001",
            category="airworthiness",
            result=CheckResult.WARNING,
            observed=observed,
            threshold=threshold,
            message="Airframe is approaching its service interval.",
        )

    return CheckDetail(
        check_id="MNT-001",
        category="airworthiness",
        result=CheckResult.CLEAR,
        observed=observed,
        threshold=threshold,
        message="Airframe is within its service interval.",
    )


def _check_aircraft_state(*, aircraft: AircraftRecord) -> CheckDetail:
    observed = {
        "status": aircraft.status,
        "is_flying": aircraft.is_flying,
        "serviceable": aircraft.serviceable,
    }
    threshold = {
        "in_service_statuses": sorted(IN_SERVICE_STATUSES),
        "serviceable": True,
    }

    # Plex's own flag, and it outranks everything else here: if the fleet
    # system says the airframe is not serviceable, no amount of RTF status
    # makes it flyable. None means the field was absent, not False.
    if aircraft.serviceable is False:
        return CheckDetail(
            check_id="MNT-002",
            category="aircraft_state",
            result=CheckResult.FAIL,
            observed=observed,
            threshold=threshold,
            message="Plex has this airframe marked as not serviceable.",
        )

    if not aircraft.status:
        return CheckDetail(
            check_id="MNT-002",
            category="aircraft_state",
            result=CheckResult.UNAVAILABLE,
            observed=observed,
            threshold=threshold,
            message="Aircraft status could not be read.",
        )

    status = aircraft.status.upper()

    if status in NOT_READY_STATUSES:
        return CheckDetail(
            check_id="MNT-002",
            category="aircraft_state",
            result=CheckResult.FAIL,
            observed=observed,
            threshold=threshold,
            message=f"Drone status is {aircraft.status!r}, which is not in service.",
        )

    if status not in IN_SERVICE_STATUSES:
        # An unrecognised status is not evidence the airframe is grounded, but
        # it is not evidence it is flyable either.
        return CheckDetail(
            check_id="MNT-002",
            category="aircraft_state",
            result=CheckResult.UNAVAILABLE,
            observed=observed,
            threshold=threshold,
            message=(
                f"Drone status {aircraft.status!r} is not a status this tool "
                f"recognises, so readiness could not be confirmed."
            ),
        )

    if aircraft.is_flying:
        # Only one flight per drone may be in the flying state at a time, so
        # this is a scheduling conflict rather than an airworthiness failure.
        return CheckDetail(
            check_id="MNT-002",
            category="aircraft_state",
            result=CheckResult.WARNING,
            observed=observed,
            threshold=threshold,
            message="Drone is already in a flying state for the requested window.",
        )

    return CheckDetail(
        check_id="MNT-002",
        category="aircraft_state",
        result=CheckResult.CLEAR,
        observed=observed,
        threshold=threshold,
        message="Drone is ready to fly and not currently airborne.",
    )
