"""Input validation for get_drone_maintenance_status.

Runs before any call to the API client. The contract has one input, so this
is short — but it stays a separate module so the tool matches the shape of
every other tool in the repo, and so "is a drone identifier present" is
checked without a network round trip.

Whether the identifier actually resolves is NOT checked here: that needs the
fleet, so it belongs to the client and surfaces as DroneNotFoundError.
"""

from dataclasses import dataclass

from tools.maintenance_status.request_response_schemas import (
    MaintenanceStatusRequest,
)


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_request(request: MaintenanceStatusRequest) -> ValidationResult:
    errors: list[str] = []

    if not isinstance(request.drone, str) or not request.drone.strip():
        errors.append("A drone identifier is required")

    return ValidationResult(errors=tuple(errors))
