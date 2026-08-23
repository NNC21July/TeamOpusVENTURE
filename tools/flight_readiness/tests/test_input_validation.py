from datetime import datetime, timedelta, timezone

from tools.flight_readiness.input_validation import (
    exceeds_forecast_horizon,
    validate_request,
)
from tools.flight_readiness.request_response_schemas import (
    FlightReadinessRequest,
    Location,
)

SG = timezone(timedelta(hours=8))
NOW = datetime(2026, 8, 25, 8, 0, tzinfo=SG)


def make_request(**overrides) -> FlightReadinessRequest:
    """A valid request, with individual fields overridden per test."""
    defaults = dict(
        drone="DRONE-001",
        planned_start_time=NOW + timedelta(hours=1),
        planned_end_time=NOW + timedelta(hours=2),
        location=Location(longitude=103.8010, latitude=1.3010),
        planned_altitude_m=60.0,
        mission_duration_min=25.0,
    )
    defaults.update(overrides)
    return FlightReadinessRequest(**defaults)


def test_valid_request_passes() -> None:
    assert validate_request(make_request(), now=NOW).is_valid


def test_missing_drone_identifier() -> None:
    result = validate_request(make_request(drone="   "), now=NOW)
    assert not result.is_valid
    assert any("drone identifier" in error for error in result.errors)


def test_end_before_start() -> None:
    result = validate_request(
        make_request(planned_end_time=NOW - timedelta(hours=5)), now=NOW
    )
    assert not result.is_valid
    assert any("later than planned_start_time" in error for error in result.errors)


def test_start_in_the_past() -> None:
    result = validate_request(
        make_request(
            planned_start_time=NOW - timedelta(hours=2),
            planned_end_time=NOW - timedelta(hours=1),
        ),
        now=NOW,
    )
    assert any("in the past" in error for error in result.errors)


def test_naive_datetime_rejected() -> None:
    # A naive datetime compares wrong against aware forecast times. Silent
    # timezone bugs are a path to a false GO, so they are rejected outright.
    result = validate_request(
        make_request(planned_start_time=datetime(2026, 8, 25, 9, 0)), now=NOW
    )
    assert any("timezone" in error for error in result.errors)


def test_longitude_out_of_range() -> None:
    result = validate_request(
        make_request(location=Location(longitude=200.0, latitude=1.3)), now=NOW
    )
    assert any("longitude" in error for error in result.errors)


def test_latitude_out_of_range() -> None:
    result = validate_request(
        make_request(location=Location(longitude=103.8, latitude=-91.0)), now=NOW
    )
    assert any("latitude" in error for error in result.errors)


def test_negative_altitude() -> None:
    result = validate_request(make_request(planned_altitude_m=-5.0), now=NOW)
    assert any("negative" in error for error in result.errors)


def test_zero_mission_duration() -> None:
    result = validate_request(make_request(mission_duration_min=0.0), now=NOW)
    assert any("positive" in error for error in result.errors)


def test_mission_duration_optional() -> None:
    assert validate_request(make_request(mission_duration_min=None), now=NOW).is_valid


def test_errors_accumulate() -> None:
    # Validation reports every problem at once rather than stopping at the first.
    result = validate_request(
        make_request(drone="", planned_altitude_m=-1.0, mission_duration_min=-5.0),
        now=NOW,
    )
    assert len(result.errors) >= 3


def test_within_forecast_horizon() -> None:
    request = make_request(
        planned_start_time=NOW + timedelta(days=6),
        planned_end_time=NOW + timedelta(days=6, hours=1),
    )
    assert not exceeds_forecast_horizon(request, now=NOW)


def test_beyond_forecast_horizon() -> None:
    # 20 days out is valid input the tool simply cannot answer: UNKNOWN, not
    # NEEDS_INFO. So it must NOT appear as a validation error.
    request = make_request(
        planned_start_time=NOW + timedelta(days=20),
        planned_end_time=NOW + timedelta(days=20, hours=1),
    )
    assert exceeds_forecast_horizon(request, now=NOW)
    assert validate_request(request, now=NOW).is_valid
