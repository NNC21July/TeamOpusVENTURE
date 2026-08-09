from dataclasses import dataclass
from datetime import datetime
from tools.route_airspace_compliance.decision_types import CheckResult

@dataclass(frozen=True)
class Waypoint:
    # One planned position along a drone route
    sequence: int
    longitude: float
    latitude: float
    altitude_m: float

@dataclass(frozen=True)
class RouteComplianceRequest:
    # Information required to check a proposed route
    waypoints: list[Waypoint]
    planned_start_time: datetime
    planned_end_time: datetime
    frz_id: str | None = None


@dataclass(frozen=True)
class NfzRecord:
    # NFZ information needed by the compliance checker
    nfz_id: str
    name: str
    zone_type: str
    minimum_altitude_m: float | None
    maximum_altitude_m: float | None
    valid_from: datetime | None
    valid_until: datetime | None

@dataclass(frozen=True)
class NfzMatch:
    # Relevant details about an NFZ that conflicts with a waypoint
    nfz_id: str
    name: str
    zone_type: str
    altitude_conflict: bool
    time_conflict: bool

@dataclass(frozen=True)
class WaypointCheckResult:
    # The NFZ compliance result for one waypoint
    sequence: int
    result: CheckResult
    matched_nfzs: tuple[NfzMatch, ...] = ()
    message: str | None = None
