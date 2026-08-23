"""Endurance predictor: projected flight time against mission duration.

    required  = mission_duration + reserve_minutes
    available = max_flight_time x state_of_health x wind_penalty x charge_fraction

The wind penalty couples this predictor to the weather: endurance falls
materially in strong wind as the aircraft works to hold position. That coupling
is deliberate, not a layering violation — it is why `weather` is a parameter.

Pure. Never fetches, never raises.
"""

from tools.flight_readiness.decision_types import CheckResult
from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    BatteryRecord,
    CheckDetail,
    WeatherRecord,
)
from tools.flight_readiness.specs.thresholds import (
    ASSUMPTION_TEXT,
    BATTERY_RESERVE_MINUTES,
    DEFAULT_STATE_OF_HEALTH,
    ENDURANCE_WARNING_MARGIN_MINUTES,
    MINIMUM_LAUNCH_CHARGE_FRACTION,
    WIND_DERATING_FACTOR,
    WIND_ENDURANCE_PENALTY,
)


def check_endurance(
    *,
    battery: BatteryRecord,
    aircraft: AircraftRecord,
    mission_duration_min: float | None,
    weather: WeatherRecord | None = None,
) -> CheckDetail:
    rated_minutes = aircraft.max_flight_time_min

    if rated_minutes is None:
        return CheckDetail(
            check_id="BAT-001",
            category="battery_endurance",
            result=CheckResult.UNAVAILABLE,
            observed={"required_min": mission_duration_min},
            message=(
                f"No rated flight time known for model {aircraft.model!r}; "
                "endurance could not be assessed."
            ),
        )

    if mission_duration_min is None:
        return CheckDetail(
            check_id="BAT-001",
            category="battery_endurance",
            result=CheckResult.UNAVAILABLE,
            threshold={"rated_flight_time_min": rated_minutes},
            message="Mission duration unknown; endurance could not be assessed.",
        )

    if battery.state_of_charge is None:
        return CheckDetail(
            check_id="BAT-001",
            category="battery_endurance",
            result=CheckResult.UNAVAILABLE,
            observed={"required_min": mission_duration_min},
            threshold={"rated_flight_time_min": rated_minutes},
            message="Battery state of charge unavailable; endurance could not be assessed.",
        )

    assumptions = [ASSUMPTION_TEXT["battery_reserve"]]

    # Missing health is assumed nominal — optimistic, so it must be recorded
    # and the caller must downgrade confidence.
    state_of_health = battery.state_of_health
    if state_of_health is None:
        state_of_health = DEFAULT_STATE_OF_HEALTH
        assumptions.append(ASSUMPTION_TEXT["default_state_of_health"])

    wind_penalty = _wind_penalty(weather=weather, aircraft=aircraft)
    if wind_penalty < 1.0:
        assumptions.append(ASSUMPTION_TEXT["wind_endurance_penalty"])

    required = mission_duration_min + BATTERY_RESERVE_MINUTES
    available = rated_minutes * state_of_health * wind_penalty * battery.state_of_charge

    observed = {
        "available_min": round(available, 1),
        "required_min": round(required, 1),
        "state_of_charge": battery.state_of_charge,
        "state_of_health": state_of_health,
        "wind_penalty": round(wind_penalty, 3),
    }
    threshold = {
        "reserve_min": BATTERY_RESERVE_MINUTES,
        "rated_flight_time_min": rated_minutes,
        "minimum_launch_charge_fraction": MINIMUM_LAUNCH_CHARGE_FRACTION,
    }

    if battery.state_of_charge < MINIMUM_LAUNCH_CHARGE_FRACTION:
        return CheckDetail(
            check_id="BAT-001",
            category="battery_endurance",
            result=CheckResult.FAIL,
            observed=observed,
            threshold=threshold,
            message=(
                f"Battery charge of {battery.state_of_charge:.0%} is below the "
                f"minimum launch charge of {MINIMUM_LAUNCH_CHARGE_FRACTION:.0%}."
            ),
            assumptions=tuple(assumptions),
        )

    if available < required:
        return CheckDetail(
            check_id="BAT-001",
            category="battery_endurance",
            result=CheckResult.FAIL,
            observed=observed,
            threshold=threshold,
            message=(
                f"Projected endurance of {available:.1f} min does not cover the "
                f"{mission_duration_min:.0f} min mission plus "
                f"{BATTERY_RESERVE_MINUTES:.0f} min reserve."
            ),
            assumptions=tuple(assumptions),
        )

    if available - required < ENDURANCE_WARNING_MARGIN_MINUTES:
        return CheckDetail(
            check_id="BAT-001",
            category="battery_endurance",
            result=CheckResult.WARNING,
            observed=observed,
            threshold=threshold,
            message=(
                f"Projected endurance covers the mission by only "
                f"{available - required:.1f} min."
            ),
            assumptions=tuple(assumptions),
        )

    return CheckDetail(
        check_id="BAT-001",
        category="battery_endurance",
        result=CheckResult.CLEAR,
        observed=observed,
        threshold=threshold,
        message="Projected endurance covers mission duration with reserve.",
        assumptions=tuple(assumptions),
    )


def _wind_penalty(*, weather: WeatherRecord | None, aircraft: AircraftRecord) -> float:
    """Fraction of rated flight time still achievable in the forecast wind.

    Interpolates the WIND_ENDURANCE_PENALTY curve on sustained wind expressed
    as a fraction of the operational ceiling. Returns 1.0 (no penalty) when
    wind or the aircraft's rating is unknown — optimistic, but the wind check
    itself will already be UNAVAILABLE in that case.
    """
    if weather is None or weather.wind_sustained_ms is None:
        return 1.0
    if not aircraft.max_wind_resistance_ms:
        return 1.0

    ceiling = aircraft.max_wind_resistance_ms * WIND_DERATING_FACTOR
    if ceiling <= 0:
        return 1.0

    fraction = weather.wind_sustained_ms / ceiling
    points = WIND_ENDURANCE_PENALTY

    if fraction <= points[0][0]:
        return points[0][1]
    if fraction >= points[-1][0]:
        return points[-1][1]

    for (low_x, low_y), (high_x, high_y) in zip(points, points[1:]):
        if low_x <= fraction <= high_x:
            span = high_x - low_x
            if span == 0:
                return low_y
            weight = (fraction - low_x) / span
            return low_y + weight * (high_y - low_y)

    return points[-1][1]
