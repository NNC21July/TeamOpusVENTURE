from dataclasses import dataclass
from datetime import date, datetime

from tools.maintenance_status.status_types import MaintenanceStatus


@dataclass(frozen=True)
class MaintenanceStatusRequest:
    # A drone name, serial number or id — whatever the pilot said
    drone: str


@dataclass(frozen=True)
class DroneRef:
    # The minimum needed to find a drone's flights and look up its service plan.
    # Flights link to a drone by NAME, not id, so the name is not optional here.
    drone_id: str
    name: str | None = None
    serial_number: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class FlightRecord:
    # One recorded flight, normalised.
    #
    # Plex reports duration as a {hours, minutes, seconds} object and the date
    # as epoch milliseconds (-1 when unset), so both are converted at ingestion
    # and the calculator only ever sees seconds and a real datetime.
    flight_id: str | None = None
    drone_name: str | None = None
    status: str | None = None
    flown_on: datetime | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True)
class ServiceRecord:
    # A completed service. No Plex endpoint supplies these today — the type
    # exists so the calculator and the status rules can already handle them
    # when a maintenance endpoint appears.
    serviced_on: date
    service_type: str | None = None
    airframe_hours_at_service: float | None = None


@dataclass(frozen=True)
class MaintenanceStatusResponse:
    status: MaintenanceStatus
    drone_id: str | None = None
    model: str | None = None
    last_service_date: date | None = None
    last_service_type: str | None = None
    hours_since_service: float | None = None
    service_interval_hours: float | None = None
    next_due_hours: float | None = None
    next_due_date: date | None = None
    # Records whether the hours figure came from an aggregated Plex field or
    # was summed client-side, so the number can be audited.
    hours_source: str | None = None
    flights_counted: int | None = None
    missing_inputs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    message: str | None = None
    data_checked_at: datetime | None = None
