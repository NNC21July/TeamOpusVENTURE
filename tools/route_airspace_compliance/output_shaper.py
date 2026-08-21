from typing import Any
from tools.route_airspace_compliance.request_response_schemas import NfzMatch, RouteComplianceResponse, WaypointCheckResult


def _shape_nfz_match(match: NfzMatch) -> dict[str, Any]:
    return {
        "nfz_id": match.nfz_id,
        "name": match.name,
        "type": match.zone_type,
        "altitude_conflict": match.altitude_conflict,
        "time_conflict": match.time_conflict
    }


def _shape_waypoint_result(result: WaypointCheckResult) -> dict[str, Any]:
    return {
        "sequence": result.sequence,
        "result": result.result.value,
        "matched_nfzs": [_shape_nfz_match(match) for match in result.matched_nfzs],
        "message": result.message,
    }


def shape_route_compliance_response(response: RouteComplianceResponse) -> dict[str, Any]:
    return {
        "decision": response.decision.value,
        "route_clear": response.route_clear,
        "waypoint_results": [_shape_waypoint_result(result) for result in response.waypoint_results],
        "violations": list(response.violations),
        "warnings": list(response.warnings),
        "missing_inputs": list(response.missing_inputs),
        "required_actions": list(response.required_actions),
        "data_checked_at": (
            response.data_checked_at.isoformat()
            if response.data_checked_at is not None
            else None
        ),
    }
