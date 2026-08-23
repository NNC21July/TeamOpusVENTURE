from typing import Protocol

from tools.maintenance_status.request_response_schemas import (
    DroneRef,
    FlightRecord,
    ServiceRecord,
)


class DroneNotFoundError(RuntimeError):
    """Raised when a drone name, serial or id does not resolve to a known drone"""


class FleetDataUnavailableError(RuntimeError):
    """Raised when drone or flight records cannot be retrieved"""


class ServiceRecordsUnavailableError(RuntimeError):
    """Raised when maintenance records exist as a concept but cannot be read.

    Distinct from a drone that simply has no service history: this means the
    service could not answer, which maps to UNKNOWN rather than NEEDS_INFO.
    """


class MaintenanceClient(Protocol):
    # Fleet capability required to derive maintenance status.
    # Backed by the shared Plex API client; this tool makes no HTTP calls.
    def get_drone(self, *, drone: str) -> DroneRef:
        ...

    def get_flight_records(self, *, drone: DroneRef) -> list[FlightRecord]:
        ...

    def get_service_records(self, *, drone: DroneRef) -> list[ServiceRecord]:
        ...
