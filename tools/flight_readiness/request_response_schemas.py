from dataclasses import dataclass, field
from datetime import date, datetime

from tools.flight_readiness.decision_types import (
    CheckResult,
    ConfidenceLevel,
    OverallDecision,
)
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
    # Battery charge as a percentage, 0-100, when the pilot can read it off
    # the controller. Verified against the live sandbox: Plex exposes no
    # battery state anywhere — /aircraft/batteries and friends all 404, and a
    # drone record carries no battery field — so without either live telemetry
    # or a pilot-supplied figure the endurance check can never be assessed.
    # Plex and telemetry take precedence when either can supply it.
    battery_charge_percent: float | None = None


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
    # Plex's own airworthiness flag. None means the field was absent, which is
    # not the same as False and must not be read as "not serviceable".
    serviceable: bool | None = None
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
    # When a record summarises a window rather than an instant, these carry the
    # extremes. A single temperature would hide a cold dawn or a hot midday.
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
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


@dataclass(frozen=True)
class CheckDetail:
    # The outcome of one predictor. `observed` and `threshold` carry the numbers
    # the verdict was reached from, so the model can explain why rather than
    # simply relaying the verdict.
    check_id: str
    category: str
    result: CheckResult
    observed: dict[str, object] = field(default_factory=dict)
    threshold: dict[str, object] = field(default_factory=dict)
    source: str | None = None
    message: str | None = None
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Confidence:
    # Categorical, never numeric. `reasons` explains what limited it.
    level: ConfidenceLevel
    reasons: tuple[str, ...] = ()
    recommended_recheck: datetime | None = None


@dataclass(frozen=True)
class FlightReadinessResponse:
    # Result returned by the tool for the whole mission
    decision: OverallDecision
    confidence: Confidence | None = None
    checks: tuple[CheckDetail, ...] = ()
    blocking_factors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()
    data_checked_at: datetime | None = None
