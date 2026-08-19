from tools.vision_summarizer.input_validation import validate_request
from tools.vision_summarizer.request_response_schemas import SummarizeFlightRequest


def test_valid_request_has_no_errors() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1")
    result = validate_request(request)
    assert result.is_valid
    assert result.errors == ()


def test_valid_request_with_focus_has_no_errors() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1", focus="defects only")
    assert validate_request(request).is_valid


def test_empty_flight_id_is_invalid() -> None:
    request = SummarizeFlightRequest(flight_id="")
    result = validate_request(request)
    assert not result.is_valid
    assert "flight_id must be a non-empty string" in result.errors


def test_whitespace_only_flight_id_is_invalid() -> None:
    request = SummarizeFlightRequest(flight_id="   ")
    result = validate_request(request)
    assert not result.is_valid
    assert "flight_id must be a non-empty string" in result.errors


def test_non_string_flight_id_is_invalid() -> None:
    request = SummarizeFlightRequest(flight_id=123)  # type: ignore[arg-type]
    result = validate_request(request)
    assert not result.is_valid
    assert "flight_id must be a non-empty string" in result.errors


def test_none_flight_id_is_invalid() -> None:
    request = SummarizeFlightRequest(flight_id=None)  # type: ignore[arg-type]
    result = validate_request(request)
    assert not result.is_valid
    assert "flight_id must be a non-empty string" in result.errors


def test_none_focus_is_valid() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1", focus=None)
    assert validate_request(request).is_valid


def test_empty_focus_is_invalid() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1", focus="")
    result = validate_request(request)
    assert not result.is_valid
    assert "focus, if provided, must be a non-empty string" in result.errors


def test_whitespace_only_focus_is_invalid() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1", focus="   ")
    result = validate_request(request)
    assert not result.is_valid
    assert "focus, if provided, must be a non-empty string" in result.errors


def test_non_string_focus_is_invalid() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1", focus=42)  # type: ignore[arg-type]
    result = validate_request(request)
    assert not result.is_valid
    assert "focus, if provided, must be a non-empty string" in result.errors


def test_invalid_flight_id_and_focus_both_reported() -> None:
    request = SummarizeFlightRequest(flight_id="", focus="")
    result = validate_request(request)
    assert not result.is_valid
    assert len(result.errors) == 2
