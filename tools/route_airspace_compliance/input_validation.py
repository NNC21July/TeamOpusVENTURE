import math
from dataclasses import dataclass
from datetime import datetime
from tools.route_airspace_compliance.request_response_schemas import RouteComplianceRequest, Waypoint


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_request(request: RouteComplianceRequest) -> ValidationResult:
    errors: list[str] = []

    if not request.waypoints:
        errors.append("At least one waypoint is required")
    else:
        for expected_sequence, waypoint in enumerate(request.waypoints, start=1):
            errors.extend(_validate_waypoint(waypoint=waypoint,
                          expected_sequence=expected_sequence))

    start_is_valid = _validate_timestamp(
        value=request.planned_start_time, field_name="planned_start_time", errors=errors)
    end_is_valid = _validate_timestamp(
        value=request.planned_end_time, field_name="planned_end_time", errors=errors)

    if (start_is_valid and end_is_valid and request.planned_end_time <= request.planned_start_time):
        errors.append("planned_end_time must be later than planned_start_time")

    if request.frz_id is not None:
        if not isinstance(request.frz_id, str) or not request.frz_id.strip():
            errors.append("frz_id must be a non-empty string")

    return ValidationResult(errors=tuple(errors))


def _validate_waypoint(waypoint: Waypoint, expected_sequence: int) -> list[str]:
    if not isinstance(waypoint, Waypoint):
        return [f"Waypoint {expected_sequence} has an invalid structure"]

    errors: list[str] = []

    if type(waypoint.sequence) != int:
        errors.append(
            f"Waypoint {expected_sequence} sequence must be an integer")
    elif waypoint.sequence != expected_sequence:
        errors.append(
            "Waypoint sequences must start at 1 and increase by 1 in route order.")

    if not _is_finite_num(waypoint.longitude):
        errors.append(
            f"Waypoint {expected_sequence} longitude must be a valid number")
    elif not -180 <= waypoint.longitude <= 180:
        errors.append(
            f"Waypoint {expected_sequence} longitude must be between -180 and 180")

    if not _is_finite_num(waypoint.latitude):
        errors.append(
            f"Waypoint {expected_sequence} latitude must be a valid number")
    elif not -90 <= waypoint.latitude <= 90:
        errors.append(
            f"Waypoint {expected_sequence} latitude must be between -90 and 90")

    if not _is_finite_num(waypoint.altitude_m):
        errors.append(
            f"Waypoint {expected_sequence} altitude_m must be a valid number")
    elif waypoint.altitude_m < 0:
        errors.append(
            f"Waypoint {expected_sequence} altitude_m cannot be negative")

    return errors


def _validate_timestamp(value: datetime, field_name: str, errors: list[str]) -> bool:
    if not isinstance(value, datetime):
        errors.append(f"{field_name} must be a valid datetime")
        return False

    if value.tzinfo is None or value.utcoffset() is None:
        errors.append(f"{field_name} must include timezone information")
        return False

    return True


def _is_finite_num(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))
