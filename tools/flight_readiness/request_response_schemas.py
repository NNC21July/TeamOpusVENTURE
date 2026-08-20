from dataclasses import dataclass
from datetime import date, datetime

from tools.maintenance_status.status_types import MaintenanceStatus


@dataclass(frozen=True)
class Location:
    # Ground position the mission is flown over
    longitude: float
    latitude: float


@dataclass(frozen=True)
class FlightReadinessRequest:
    # Information required to assess whether a mission can fly
    drone: str
    planned_start_time: datetime
    planned_end_time: datetime
    location: Location
    planned_altitude_m: float
    mission_duration_min: float | None = None


@dataclass(frozen=True)
class AircraftRecord:
    # Aircraft state and operating limits needed by the predictors.
    # Limits are None when neither Plex nor the local specs table supplies them,
    # which the predictors must treat as UNAVAILABLE rather than permissive.
    drone_id: str
    model: str
    status: str
    name: str | None = None
    max_wind_resistance_ms: float | None = None
    max_flight_time_min: float | None = None
    operating_temp_min_c: float | None = None
    operating_temp_max_c: float | None = None
    precipitation_tolerance_mm_h: float | None = None
    is_flying: bool = False
    limits_source: str | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True)
class BatteryRecord:
    # Battery state needed by the endurance predictor.
    # state_of_charge and state_of_health are fractions in [0, 1].
    battery_id: str | None = None
    state_of_charge: float | None = None
    state_of_health: float | None = None
    cycle_count: int | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True)
class WeatherRecord:
    # Weather for the planned window, already normalised to m/s and degrees C
    # by the source client, so the predictor does not care which source it came from.
    source: str
    valid_at: datetime
    wind_sustained_ms: float | None = None
    wind_gust_ms: float | None = None
    wind_altitude_m: float | None = None
    precipitation_mm_h: float | None = None
    temperature_c: float | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True)
class MaintenanceSnapshot:
    # The subset of Tool 2's output that the airworthiness predictor reads
    status: MaintenanceStatus
    hours_since_service: float | None = None
    service_interval_hours: float | None = None
    last_service_date: date | None = None
    next_due_date: date | None = None
    hours_source: str | None = None
    checked_at: datetime | None = None
