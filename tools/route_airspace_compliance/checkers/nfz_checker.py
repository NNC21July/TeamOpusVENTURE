from datetime import datetime
from tools.route_airspace_compliance.client_protocol import AirspaceClient, AirspaceDataUnavailableError
from tools.route_airspace_compliance.request_response_schemas import Waypoint, WaypointCheckResult
from tools.route_airspace_compliance.decision_types import CheckResult
from tools.route_airspace_compliance.request_response_schemas import NfzMatch, Waypoint, WaypointCheckResult

def check_waypoint_against_nfzs(*, waypoint:Waypoint, planned_start_time:datetime, planned_end_time:datetime, client:AirspaceClient) -> WaypointCheckResult:
    try:
        nfzs = client.query_nfzs(longitude=waypoint.longitude, latitude=waypoint.latitude)
    except AirspaceDataUnavailableError:
        return WaypointCheckResult(sequence=waypoint.sequence, result=CheckResult.UNAVAILABLE, message=f"Airspace data is unavailable for waypoint {waypoint.sequence}")
    
    matches: list[NfzMatch] = []
    has_unavailable_data = False
    
    for nfz in nfzs:
        min_altitude = nfz.minimum_altitude_m
        max_altitude = nfz.maximum_altitude_m
        valid_from = nfz.valid_from
        valid_until = nfz.valid_until
        
        if (min_altitude is None or max_altitude is None or valid_from is None or valid_until is None):
            has_unavailable_data = True
            continue
        if (valid_from.utcoffset() is None or valid_until.utcoffset() is None):
            has_unavailable_data = True
            continue
        if (min_altitude > max_altitude or valid_from > valid_until):
            has_unavailable_data = True
            continue
        
        altitude_conflict = min_altitude <= waypoint.altitude_m <= max_altitude
        time_conflict = planned_start_time <= valid_until and planned_end_time >= valid_from
        
        if altitude_conflict and time_conflict:
            matches.append(NfzMatch(
                nfz_id=nfz.nfz_id,
                name=nfz.name,
                zone_type=nfz.zone_type,
                altitude_conflict=True,
                time_conflict=True)
            )
            
    if matches:
        return WaypointCheckResult(
            sequence=waypoint.sequence,
            result=CheckResult.VIOLATION,
            matched_nfzs=tuple(matches),
            message=f"Waypoint {waypoint.sequence} conflicts with {len(matches)} active NFZ(s)"
        )
    if has_unavailable_data:
        return WaypointCheckResult(
            sequence=waypoint.sequence,
            result=CheckResult.UNAVAILABLE,
            message=f"Some NFZ data for waypoint {waypoint.sequence} could not be interpreted"
        )
    
    return WaypointCheckResult(
        sequence=waypoint.sequence,
        result=CheckResult.CLEAR,
        message=f"No active NFZ conflict found for waypoint {waypoint.sequence}"
    )