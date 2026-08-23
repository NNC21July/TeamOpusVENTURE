from typing import Protocol

from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    BatteryRecord,
    MaintenanceSnapshot,
)


class AircraftDataUnavailableError(RuntimeError):
    """Raised when required aircraft or battery information cannot be retrieved"""


class DroneNotFoundError(RuntimeError):
    """Raised when a drone name or serial does not resolve to a known drone"""


class MaintenanceDataUnavailableError(RuntimeError):
    """Raised when maintenance information cannot be retrieved"""


class AircraftClient(Protocol):
    # Aircraft capability required by the endurance and airworthiness predictors.
    # Backed by the shared Plex API client; this tool never makes HTTP calls itself.
    def get_aircraft(self, *, drone: str) -> AircraftRecord:
        ...

    def get_battery(self, *, drone_id: str) -> BatteryRecord:
        ...


class MaintenanceReader(Protocol):
    # Maintenance capability required by the airworthiness predictor.
    # Backed by get_drone_maintenance_status (Tool 2).
    def get_maintenance_status(self, *, drone_id: str) -> MaintenanceSnapshot:
        ...
