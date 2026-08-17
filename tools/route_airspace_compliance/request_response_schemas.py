from dataclasses import dataclass
from datetime import datetime
from tools.route_airspace_compliance.decision_types import CheckResult, OverallDecision
from tools.route_airspace_compliance.recurrence_schemas import RecurringSchedule

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
    recurring_schedule: RecurringSchedule | None = None

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


@dataclass(frozen=True)
class RouteComplianceResponse:
    # Result returned by the tool for the whole route
    decision: OverallDecision
    route_clear: bool
    waypoint_results: tuple[WaypointCheckResult, ...] = ()
    violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    required_actions: tuple[str, ...] = ()
    data_checked_at: datetime | None = None
    