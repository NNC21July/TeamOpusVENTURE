from datetime import datetime, timezone

import pytest

from tools.route_airspace_compliance.decision_types import CheckResult, OverallDecision
from tools.route_airspace_compliance.request_response_schemas import (
    NfzMatch,
    RouteComplianceResponse,
    WaypointCheckResult,
)


output_shaper_module = pytest.importorskip(
    "tools.route_airspace_compliance.output_shaper",
)
shape_route_compliance_response = (
    output_shaper_module.shape_route_compliance_response
)


def test_shapes_block_response_into_json_friendly_dictionary() -> None:
    checked_at = datetime(2026, 8, 21, 4, 30, tzinfo=timezone.utc)
    response = RouteComplianceResponse(
        decision=OverallDecision.BLOCK,
        route_clear=False,
        waypoint_results=(
            WaypointCheckResult(
                sequence=1,
                result=CheckResult.VIOLATION,
                matched_nfzs=(
                    NfzMatch(
                        nfz_id="NFZ-001",
                        name="Restricted Area",
                        zone_type="restricted_area",
                        altitude_conflict=True,
                        time_conflict=True,
                    ),
                ),
                message="Waypoint 1 conflicts with an active NFZ",
            ),
        ),
        violations=("Waypoint 1 conflicts with an active NFZ",),
        required_actions=("Revise the route",),
        data_checked_at=checked_at,
    )

    assert shape_route_compliance_response(response) == {
        "decision": "BLOCK",
        "route_clear": False,
        "waypoint_results": [
            {
                "sequence": 1,
                "result": "VIOLATION",
                "matched_nfzs": [
                    {
                        "nfz_id": "NFZ-001",
                        "name": "Restricted Area",
                        "type": "restricted_area",
                        "altitude_conflict": True,
                        "time_conflict": True,
                    }
                ],
                "message": "Waypoint 1 conflicts with an active NFZ",
            }
        ],
        "violations": ["Waypoint 1 conflicts with an active NFZ"],
        "warnings": [],
        "missing_inputs": [],
        "required_actions": ["Revise the route"],
        "data_checked_at": "2026-08-21T04:30:00+00:00",
    }
