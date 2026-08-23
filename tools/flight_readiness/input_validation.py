"""Input validation for check_flight_readiness.

Runs before any call to the API client or a weather source. No external
request is made until basic input has passed.

Two distinct outcomes live here and must not be confused:

  validate_request()        -> failures map to NEEDS_INFO. The input was wrong.
  exceeds_forecast_horizon() -> maps to UNKNOWN. The input was valid; the
                                capability was not.

`now` is passed in rather than read from the clock, so the past-start and
horizon rules are testable without freezing time.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from tools.flight_readiness.request_response_schemas import FlightReadinessRequest
from tools.flight_readiness.specs.thresholds import OPEN_METEO_FORECAST_HORIZON_DAYS


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_request(request: FlightReadinessRequest, *, now: datetime) -> ValidationResult:
    errors: list[str] = []

    if not isinstance(request.drone, str) or not request.drone.strip():
        errors.append("A drone identifier is required")

    start_is_valid = _validate_timestamp(
        value=request.planned_start_time, field_name="planned_start_time", errors=errors
    )
    end_is_valid = _validate_timestamp(
        value=request.planned_end_time, field_name="planned_end_time", errors=errors
    )

    if start_is_valid and end_is_valid and request.planned_end_time <= request.planned_start_time:
        errors.append("planned_end_time must be later than planned_start_time")

    if start_is_valid and request.planned_start_time < now:
        errors.append("planned_start_time is in the past")

    errors.extend(_validate_location(request.location))

    if not _is_finite_num(request.planned_altitude_m):
        errors.append("planned_altitude_m must be a valid number")
    elif request.planned_altitude_m < 0:
        errors.append("planned_altitude_m cannot be negative")

    if request.mission_duration_min is not None:
        if not _is_finite_num(request.mission_duration_min):
            errors.append("mission_duration_min must be a valid number")
        elif request.mission_duration_min <= 0:
            errors.append("mission_duration_min must be positive")

    return ValidationResult(errors=tuple(errors))


def exceeds_forecast_horizon(request: FlightReadinessRequest, *, now: datetime) -> bool:
    """True when the planned start is beyond what any weather source can reach.

    Deliberately not a validation error: the request was well formed, the tool
    simply cannot answer it. The caller returns UNKNOWN, not NEEDS_INFO.
    """
    if not isinstance(request.planned_start_time, datetime):
        return False
    if request.planned_start_time.tzinfo is None:
        return False
    return request.planned_start_time > now + timedelta(days=OPEN_METEO_FORECAST_HORIZON_DAYS)


def _validate_location(location: object) -> list[str]:
    from tools.flight_readiness.request_response_schemas import Location

    if not isinstance(location, Location):
        return ["A location with longitude and latitude is required"]

    errors: list[str] = []

    if not _is_finite_num(location.longitude):
        errors.append("longitude must be a valid number")
    elif not -180 <= location.longitude <= 180:
        errors.append("longitude must be between -180 and 180")

    if not _is_finite_num(location.latitude):
        errors.append("latitude must be a valid number")
    elif not -90 <= location.latitude <= 90:
        errors.append("latitude must be between -90 and 90")

    return errors


def _validate_timestamp(value: object, field_name: str, errors: list[str]) -> bool:
    if not isinstance(value, datetime):
        errors.append(f"{field_name} must be a valid datetime")
        return False

    # A naive datetime compares wrong against timezone-aware forecast times,
    # which is a silent path to a false GO.
    if value.tzinfo is None or value.utcoffset() is None:
        errors.append(f"{field_name} must include timezone information")
        return False

    return True


def _is_finite_num(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))
