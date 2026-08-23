from tools.maintenance_status.input_validation import validate_request
from tools.maintenance_status.request_response_schemas import (
    MaintenanceStatusRequest,
)


def test_a_drone_identifier_passes() -> None:
    assert validate_request(MaintenanceStatusRequest(drone="DRONE-001")).is_valid


def test_a_name_passes() -> None:
    assert validate_request(MaintenanceStatusRequest(drone="Falcon 1")).is_valid


def test_empty_identifier_fails() -> None:
    result = validate_request(MaintenanceStatusRequest(drone=""))
    assert not result.is_valid
    assert any("drone identifier" in error for error in result.errors)


def test_whitespace_only_identifier_fails() -> None:
    assert not validate_request(MaintenanceStatusRequest(drone="   ")).is_valid


def test_non_string_identifier_fails() -> None:
    assert not validate_request(MaintenanceStatusRequest(drone=None)).is_valid
    assert not validate_request(MaintenanceStatusRequest(drone=12345)).is_valid
