from dataclasses import replace
from datetime import datetime, timedelta, timezone
from tools.route_airspace_compliance.input_validation import validate_request
from tools.route_airspace_compliance.request_response_schemas import RouteComplianceRequest, Waypoint


def make_valid_request() -> RouteComplianceRequest:
    start_time = datetime(
        2026,
        8,
        10,
        9,
        0,
        tzinfo=timezone(timedelta(hours=8)),
    )

    return RouteComplianceRequest(
        waypoints=[
            Waypoint(
                sequence=1,
                longitude=103.8001,
                latitude=1.3001,
                altitude_m=20,
            ),
            Waypoint(
                sequence=2,
                longitude=103.8010,
                latitude=1.3010,
                altitude_m=40,
            ),
        ],
        planned_start_time=start_time,
        planned_end_time=start_time + timedelta(hours=1),
    )


def test_valid_request_passes_validation() -> None:
    result = validate_request(make_valid_request())

    assert result.is_valid
    assert result.errors == ()


def test_empty_waypoint_list_fails_validation() -> None:
    request = replace(make_valid_request(), waypoints=[])

    result = validate_request(request)

    assert not result.is_valid
    assert "At least one waypoint is required" in result.errors


def test_invalid_longitude_fails_validation() -> None:
    request = replace(
        make_valid_request(),
        waypoints=[
            Waypoint(
                sequence=1,
                longitude=181,
                latitude=1.3001,
                altitude_m=20,
            )
        ],
    )

    result = validate_request(request)

    assert not result.is_valid
    assert any("longitude" in error for error in result.errors)


def test_invalid_latitude_fails_validation() -> None:
    request = replace(
        make_valid_request(),
        waypoints=[
            Waypoint(
                sequence=1,
                longitude=103.8001,
                latitude=91,
                altitude_m=20,
            )
        ],
    )

    result = validate_request(request)

    assert not result.is_valid
    assert any("latitude" in error for error in result.errors)


def test_negative_altitude_fails_validation() -> None:
    request = replace(
        make_valid_request(),
        waypoints=[
            Waypoint(
                sequence=1,
                longitude=103.8001,
                latitude=1.3001,
                altitude_m=-1,
            )
        ],
    )

    result = validate_request(request)

    assert not result.is_valid
    assert any("altitude_m" in error for error in result.errors)


def test_incorrect_sequence_fails_validation() -> None:
    request = replace(
        make_valid_request(),
        waypoints=[
            Waypoint(
                sequence=2,
                longitude=103.8001,
                latitude=1.3001,
                altitude_m=20,
            )
        ],
    )

    result = validate_request(request)

    assert not result.is_valid
    assert any("sequences" in error for error in result.errors)


def test_start_timestamp_without_timezone_fails_validation() -> None:
    request = replace(
        make_valid_request(),
        planned_start_time=datetime(2026, 8, 10, 9, 0),
    )

    result = validate_request(request)

    assert not result.is_valid
    assert any(
        "planned_start_time" in error and "timezone" in error
        for error in result.errors
    )


def test_end_timestamp_without_timezone_fails_validation() -> None:
    request = replace(
        make_valid_request(),
        planned_end_time=datetime(2026, 8, 10, 10, 0),
    )

    result = validate_request(request)

    assert not result.is_valid
    assert any(
        "planned_end_time" in error and "timezone" in error
        for error in result.errors
    )


def test_end_time_before_start_time_fails_validation() -> None:
    request = make_valid_request()
    request = replace(
        request,
        planned_end_time=request.planned_start_time - timedelta(minutes=1),
    )

    result = validate_request(request)

    assert not result.is_valid
    assert any("later than" in error for error in result.errors)


def test_blank_frz_id_fails_validation() -> None:
    request = replace(make_valid_request(), frz_id="   ")

    result = validate_request(request)

    assert not result.is_valid
    assert any("frz_id" in error for error in result.errors)
