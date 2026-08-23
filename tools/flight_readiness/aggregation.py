"""Combine independent check results into one decision plus a confidence level.

This is where the tool's fail-closed principle is actually implemented:

  * NO_GO outranks UNKNOWN. If one factor definitively fails, the assessment
    refuses even when another factor could not be assessed. Enough is known
    to say no.
  * Absence of a verdict is never approval. UNAVAILABLE degrades the decision
    to UNKNOWN; it never clears.
  * Low confidence never upgrades. It may downgrade GO to GO_WITH_WARNINGS,
    and never softens NO_GO.

Pure. `now` is passed in rather than read from the clock.
"""

from datetime import datetime, timedelta

from tools.flight_readiness.decision_types import (
    CheckResult,
    ConfidenceLevel,
    OverallDecision,
)
from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    BatteryRecord,
    CheckDetail,
    Confidence,
    MaintenanceSnapshot,
    WeatherRecord,
)
from tools.flight_readiness.specs.thresholds import (
    BATTERY_STATE_MAX_AGE_HOURS,
    LIVE_OBSERVATION_HORIZON_HOURS,
    MAINTENANCE_RECORD_MAX_AGE_DAYS,
    NEA_FORECAST_HORIZON_DAYS,
)

# Weakest first. Used to take the worst of several confidence factors.
_CONFIDENCE_RANK: dict[ConfidenceLevel, int] = {
    ConfidenceLevel.LOW: 0,
    ConfidenceLevel.MEDIUM: 1,
    ConfidenceLevel.HIGH: 2,
}


def aggregate_decision(checks: tuple[CheckDetail, ...]) -> OverallDecision:
    """Reduce individual check results to one overall decision.

    Order matters and encodes the precedence rules. FAIL is tested before
    UNAVAILABLE so a definite failure is never masked by a missing source.
    """
    if not checks:
        return OverallDecision.UNKNOWN

    results = {check.result for check in checks}

    if CheckResult.FAIL in results:
        return OverallDecision.NO_GO
    if CheckResult.UNAVAILABLE in results:
        return OverallDecision.UNKNOWN
    if CheckResult.WARNING in results:
        return OverallDecision.GO_WITH_WARNINGS
    return OverallDecision.GO


def apply_confidence(
    decision: OverallDecision, confidence: Confidence | None
) -> OverallDecision:
    """Let low confidence downgrade a clean GO, and nothing else.

    A GO reached on a six-day-out forecast is not the same claim as a GO
    reached on live observations, and should not read identically to a pilot.
    """
    if confidence is None:
        return decision
    if decision is OverallDecision.GO and confidence.level is ConfidenceLevel.LOW:
        return OverallDecision.GO_WITH_WARNINGS
    return decision


def derive_confidence(
    *,
    now: datetime,
    planned_start_time: datetime,
    checks: tuple[CheckDetail, ...] = (),
    aircraft: AircraftRecord | None = None,
    battery: BatteryRecord | None = None,
    maintenance: MaintenanceSnapshot | None = None,
    weather: WeatherRecord | None = None,
    mission_duration_derived: bool = False,
) -> Confidence:
    """Take the weakest of forecast horizon, data freshness and input completeness."""
    reasons: list[str] = []

    horizon_level, horizon_reason = _horizon_confidence(
        now=now, planned_start_time=planned_start_time
    )
    if horizon_reason:
        reasons.append(horizon_reason)

    freshness_level, freshness_reasons = _freshness_confidence(
        now=now,
        aircraft=aircraft,
        battery=battery,
        maintenance=maintenance,
        weather=weather,
    )
    reasons.extend(freshness_reasons)

    completeness_level, completeness_reasons = _completeness_confidence(
        checks=checks, mission_duration_derived=mission_duration_derived
    )
    reasons.extend(completeness_reasons)

    level = min(
        (horizon_level, freshness_level, completeness_level),
        key=lambda candidate: _CONFIDENCE_RANK[candidate],
    )

    recheck = None
    if level is not ConfidenceLevel.HIGH and planned_start_time > now:
        # Recommend rechecking a day out, or halfway there for near-term flights.
        day_before = planned_start_time - timedelta(days=1)
        recheck = day_before if day_before > now else now + (planned_start_time - now) / 2

    return Confidence(level=level, reasons=tuple(reasons), recommended_recheck=recheck)


def _horizon_confidence(
    *, now: datetime, planned_start_time: datetime
) -> tuple[ConfidenceLevel, str | None]:
    lead = planned_start_time - now

    if lead <= timedelta(hours=LIVE_OBSERVATION_HORIZON_HOURS):
        return ConfidenceLevel.HIGH, None

    if lead <= timedelta(days=NEA_FORECAST_HORIZON_DAYS):
        return (
            ConfidenceLevel.MEDIUM,
            f"Planned start is {_describe(lead)} ahead; assessed on forecast "
            f"rather than live observations.",
        )

    return (
        ConfidenceLevel.LOW,
        f"Planned start is {_describe(lead)} ahead; forecast uncertainty is "
        f"wide at this horizon.",
    )


def _freshness_confidence(
    *,
    now: datetime,
    aircraft: AircraftRecord | None,
    battery: BatteryRecord | None,
    maintenance: MaintenanceSnapshot | None,
    weather: WeatherRecord | None,
) -> tuple[ConfidenceLevel, list[str]]:
    reasons: list[str] = []
    level = ConfidenceLevel.HIGH

    if battery is not None and battery.observed_at is not None:
        age = now - battery.observed_at
        if age > timedelta(hours=BATTERY_STATE_MAX_AGE_HOURS):
            level = ConfidenceLevel.MEDIUM
            reasons.append(f"Battery state last updated {_describe(age)} ago.")

    if maintenance is not None and maintenance.checked_at is not None:
        age = now - maintenance.checked_at
        if age > timedelta(days=MAINTENANCE_RECORD_MAX_AGE_DAYS):
            level = ConfidenceLevel.MEDIUM
            reasons.append(f"Maintenance records last read {_describe(age)} ago.")

    if aircraft is not None and aircraft.observed_at is not None:
        age = now - aircraft.observed_at
        if age > timedelta(hours=BATTERY_STATE_MAX_AGE_HOURS):
            level = ConfidenceLevel.MEDIUM
            reasons.append(f"Aircraft state last updated {_describe(age)} ago.")

    if aircraft is not None and aircraft.limits_source == "local_specs":
        level = ConfidenceLevel.MEDIUM
        reasons.append(
            "Operating limits came from the local specification table, not Plex."
        )

    if weather is not None and weather.observed_at is not None:
        age = now - weather.observed_at
        if age > timedelta(hours=6):
            level = ConfidenceLevel.MEDIUM
            reasons.append(f"Weather data is {_describe(age)} old.")

    return level, reasons


def _completeness_confidence(
    *, checks: tuple[CheckDetail, ...], mission_duration_derived: bool
) -> tuple[ConfidenceLevel, list[str]]:
    reasons: list[str] = []
    level = ConfidenceLevel.HIGH

    if mission_duration_derived:
        level = ConfidenceLevel.MEDIUM
        reasons.append(
            "Mission duration was derived from the flight window rather than supplied."
        )

    # Any check that leaned on an assumption was assessed on degraded input.
    assumed = {assumption for check in checks for assumption in check.assumptions}
    if any("unavailable" in assumption.lower() for assumption in assumed):
        level = ConfidenceLevel.MEDIUM
        reasons.append("One or more checks were assessed on assumed values.")

    return level, reasons


def collect_blocking_factors(checks: tuple[CheckDetail, ...]) -> tuple[str, ...]:
    return tuple(
        check.message
        for check in checks
        if check.result is CheckResult.FAIL and check.message
    )


def collect_warnings(checks: tuple[CheckDetail, ...]) -> tuple[str, ...]:
    return tuple(
        check.message
        for check in checks
        if check.result in (CheckResult.WARNING, CheckResult.UNAVAILABLE)
        and check.message
    )


def collect_assumptions(checks: tuple[CheckDetail, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for check in checks:
        for assumption in check.assumptions:
            if assumption not in seen:
                seen.append(assumption)
    return tuple(seen)


def _describe(delta: timedelta) -> str:
    total_hours = delta.total_seconds() / 3600
    if total_hours < 1:
        return f"{int(delta.total_seconds() // 60)} minutes"
    if total_hours < 48:
        return f"{int(total_hours)} hours"
    return f"{int(total_hours // 24)} days"
