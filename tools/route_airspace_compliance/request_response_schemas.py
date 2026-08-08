from dataclasses import dataclass
from datetime import datetime


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
