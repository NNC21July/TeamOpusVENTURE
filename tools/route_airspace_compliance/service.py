from datetime import datetime, timezone
from tools.route_airspace_compliance.client_protocol import AirspaceClient
from tools.route_airspace_compliance.request_response_schemas import RouteComplianceRequest, RouteComplianceResponse
from tools.route_airspace_compliance.checkers.nfz_checker import check_waypoint_against_nfzs
from tools.route_airspace_compliance.decision_types import CheckResult, OverallDecision
from tools.route_airspace_compliance.input_validation import validate_request

def check_route_airspace_compliance(*, request: RouteComplianceRequest, client: AirspaceClient) -> RouteComplianceResponse:
    validation = validate_request(request)
    if not validation.is_valid:
        return RouteComplianceResponse(
            decision=OverallDecision.NEEDS_INFO,
            route_clear=False,
            missing_inputs=validation.errors,
            required_actions=("Correct the invalid route information and try again",)
        )
    
    waypoint_results = []
    for waypoint in request.waypoints:
        result = check_waypoint_against_nfzs(
            waypoint=waypoint,
            planned_start_time=request.planned_start_time,
            planned_end_time=request.planned_end_time,
            client=client
        )
        waypoint_results.append(result)
        
    has_violation = any(result.result is CheckResult.VIOLATION for result in waypoint_results)
    has_unavailable = any(result.result is CheckResult.UNAVAILABLE for result in waypoint_results)
    has_warning = any(result.result is CheckResult.WARNING for result in waypoint_results)
    
    frz_check_unavailable = request.frz_id is not None
    
    if has_violation:
        decision = OverallDecision.BLOCK
        required_actions = ("Revise the route or obtain the required airspace approval",)
    elif has_unavailable or frz_check_unavailable:
        decision = OverallDecision.UNKNOWN
        required_actions = ("Retry when all required airspace data is available",)
    elif has_warning:
        decision = OverallDecision.PASS_WITH_WARNINGS
        required_actions = ("Review the warnings before proceeding",)
    else:
        decision = OverallDecision.PASS
        required_actions = ()
        
    violations = tuple(
        result.message
        for result in waypoint_results
        if result.result is CheckResult.VIOLATION
        and result.message is not None
    )
    warnings = tuple(
        result.message
        for result in waypoint_results
        if result.result is CheckResult.WARNING
        and result.message is not None
    )
    route_clear = decision in (
        OverallDecision.PASS,
        OverallDecision.PASS_WITH_WARNINGS,
    )

    return RouteComplianceResponse(
        decision=decision,
        route_clear=route_clear,
        waypoint_results=tuple(waypoint_results),
        violations=violations,
        warnings=warnings,
        required_actions=required_actions,
        data_checked_at=datetime.now(timezone.utc),
    )