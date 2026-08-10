from dataclasses import replace
from tools.route_airspace_compliance.decision_types import CheckResult, OverallDecision
from tools.route_airspace_compliance.service import check_route_airspace_compliance
from tools.route_airspace_compliance.request_response_schemas import RouteComplianceRequest, Waypoint
from tools.route_airspace_compliance.tests.fakes import FakeAirspaceClient
from tools.route_airspace_compliance.tests.fixtures.nfz_responses import ACTIVE_RESTRICTED_NFZ, PLANNED_END_TIME, PLANNED_START_TIME

def make_valid_request() -> RouteComplianceRequest:
    return RouteComplianceRequest(
        waypoints=[
            Waypoint(
                sequence=1,
                longitude=103.8001,
                latitude=1.3001,
                altitude_m=20
            )
        ],
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME
    )
    
def test_invalid_request_returns_needs_info_without_client_call() -> None:
    request = RouteComplianceRequest(
        waypoints=[],
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME
    )
    client = FakeAirspaceClient()
    result = check_route_airspace_compliance(
        request=request,
        client=client
    )
    assert result.decision is OverallDecision.NEEDS_INFO
    assert result.route_clear is False
    assert "At least one waypoint is required" in result.missing_inputs
    assert client.queries == [] # client was never called
    
def test_valid_route_with_no_nfzs_returns_pass() -> None:
    request = make_valid_request()
    client = FakeAirspaceClient()
    result = check_route_airspace_compliance(
        request=request,
        client=client,
    )
    assert result.decision is OverallDecision.PASS
    assert result.route_clear is True
    assert len(result.waypoint_results) == 1
    assert result.waypoint_results[0].result is CheckResult.CLEAR
    assert result.violations == ()
    assert result.missing_inputs == ()
    assert client.queries == [(103.8001, 1.3001)]
    
def test_active_nfz_returns_block() -> None:
    request = make_valid_request()
    client = FakeAirspaceClient(
        nfzs=[ACTIVE_RESTRICTED_NFZ]
    )
    result = check_route_airspace_compliance(
        request=request,
        client=client
    )
    assert result.decision is OverallDecision.BLOCK
    assert result.route_clear is False
    assert len(result.waypoint_results) == 1
    
    waypoint_result = result.waypoint_results[0]
    assert waypoint_result.result is CheckResult.VIOLATION
    assert len(waypoint_result.matched_nfzs) == 1
    
    matched_nfz = waypoint_result.matched_nfzs[0]
    assert matched_nfz.nfz_id == ACTIVE_RESTRICTED_NFZ.nfz_id
    assert len(result.violations) == 1
    assert client.queries == [(103.8001, 1.3001)]
    
def test_unavailable_nfz_data_returns_unknown() -> None:
    request = make_valid_request()
    client = FakeAirspaceClient(
        unavailable=True
    )
    result = check_route_airspace_compliance(
        request=request,
        client=client,
    )
    assert result.decision is OverallDecision.UNKNOWN
    assert result.route_clear is False
    assert len(result.waypoint_results) == 1
    
    waypoint_result = result.waypoint_results[0]
    assert waypoint_result.result is CheckResult.UNAVAILABLE
    assert result.violations == ()
    assert len(result.required_actions) == 1
    assert client.queries == [(103.8001, 1.3001)]
    
def test_requested_frz_returns_unknown_until_frz_check_is_implemented() -> None:
    request = replace(
        make_valid_request(),
        frz_id="FRZ-001",
    )
    client = FakeAirspaceClient()
    result = check_route_airspace_compliance(
        request=request,
        client=client,
    )
    assert result.decision is OverallDecision.UNKNOWN
    assert result.route_clear is False
    assert len(result.waypoint_results) == 1
    assert result.waypoint_results[0].result is CheckResult.CLEAR
    assert result.violations == ()
    assert len(result.required_actions) == 1
    assert client.queries == [(103.8001, 1.3001)]

def test_route_checks_every_waypoint() -> None:
    base_request = make_valid_request()
    second_waypoint = Waypoint(
        sequence=2,
        longitude=103.8101,
        latitude=1.3101,
        altitude_m=30
    )
    request = replace(
        base_request,
        waypoints=[
            base_request.waypoints[0],
            second_waypoint,
        ]
    )
    client = FakeAirspaceClient()
    result = check_route_airspace_compliance(
        request=request,
        client=client,
    )
    assert result.decision is OverallDecision.PASS
    assert result.route_clear is True
    assert len(result.waypoint_results) == 2
    assert all(
        waypoint_result.result is CheckResult.CLEAR
        for waypoint_result in result.waypoint_results
    )
    assert client.queries == [
        (103.8001, 1.3001),
        (103.8101, 1.3101),
    ]