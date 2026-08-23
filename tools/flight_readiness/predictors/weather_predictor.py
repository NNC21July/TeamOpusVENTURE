"""Weather predictor: forecast or observed conditions against aircraft limits.

Returns three independent checks — wind, precipitation, temperature — so a
pilot sees every failing factor at once rather than one per call.

Pure. Never fetches, never reads the clock, never raises. Missing data becomes
UNAVAILABLE, which the aggregator treats as "could not assess", never as "fine".
"""

from tools.flight_readiness.decision_types import CheckResult
from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    CheckDetail,
    WeatherRecord,
)
from tools.flight_readiness.specs.thresholds import (
    ASSUMPTION_TEXT,
    WIND_DERATING_FACTOR,
    WIND_WARNING_BAND_FRACTION,
)


def check_weather(
    *, weather: WeatherRecord, aircraft: AircraftRecord
) -> tuple[CheckDetail, ...]:
    return (
        _check_wind(weather=weather, aircraft=aircraft),
        _check_precipitation(weather=weather, aircraft=aircraft),
        _check_temperature(weather=weather, aircraft=aircraft),
    )


def _check_wind(*, weather: WeatherRecord, aircraft: AircraftRecord) -> CheckDetail:
    rated = aircraft.max_wind_resistance_ms
    sustained = weather.wind_sustained_ms
    gust = weather.wind_gust_ms

    if rated is None:
        return CheckDetail(
            check_id="WX-001",
            category="weather_wind",
            result=CheckResult.UNAVAILABLE,
            observed={"sustained_ms": sustained, "gust_ms": gust},
            source=weather.source,
            message=(
                f"No wind limit known for model {aircraft.model!r}; "
                "wind could not be assessed."
            ),
        )

    if sustained is None and gust is None:
        return CheckDetail(
            check_id="WX-001",
            category="weather_wind",
            result=CheckResult.UNAVAILABLE,
            threshold={"rated_max_ms": rated},
            source=weather.source,
            message="Weather source returned no wind figures.",
        )

    ceiling = rated * WIND_DERATING_FACTOR
    band = ceiling * WIND_WARNING_BAND_FRACTION

    observed = {
        "sustained_ms": sustained,
        "gust_ms": gust,
        "altitude_m": weather.wind_altitude_m,
    }
    threshold = {"operational_ceiling_ms": ceiling, "rated_max_ms": rated}
    assumptions = [ASSUMPTION_TEXT["wind_derating"]]

    # Sustained and gust are checked separately against the same ceiling.
    # Gust is the dominant wind risk: it can fail on its own with sustained
    # wind comfortably below the limit.
    exceeded = [
        name
        for name, value in (("sustained wind", sustained), ("gust", gust))
        if value is not None and value > ceiling
    ]
    if exceeded:
        return CheckDetail(
            check_id="WX-001",
            category="weather_wind",
            result=CheckResult.FAIL,
            observed=observed,
            threshold=threshold,
            source=weather.source,
            message=(
                f"Forecast {' and '.join(exceeded)} exceeds the operational "
                f"ceiling of {ceiling:.1f} m/s."
            ),
            assumptions=tuple(assumptions),
        )

    in_band = [
        name
        for name, value in (("sustained wind", sustained), ("gust", gust))
        if value is not None and value >= band
    ]
    if in_band:
        assumptions.append(ASSUMPTION_TEXT["wind_warning_band"])
        return CheckDetail(
            check_id="WX-001",
            category="weather_wind",
            result=CheckResult.WARNING,
            observed=observed,
            threshold=threshold,
            source=weather.source,
            message=(
                f"Forecast {' and '.join(in_band)} is within the warning band "
                f"of the operational ceiling."
            ),
            assumptions=tuple(assumptions),
        )

    if gust is None:
        # Sustained wind is clear, but gust is the dominant risk factor and
        # this source does not publish one. Clearing on sustained wind alone
        # would be a false CLEAR, so this caps at WARNING.
        assumptions.append(
            "Weather source published no gust figure; wind assessed on "
            "sustained wind alone."
        )
        return CheckDetail(
            check_id="WX-001",
            category="weather_wind",
            result=CheckResult.WARNING,
            observed=observed,
            threshold=threshold,
            source=weather.source,
            message=(
                "Sustained wind is within limits, but no gust figure was "
                "available to check against the ceiling."
            ),
            assumptions=tuple(assumptions),
        )

    return CheckDetail(
        check_id="WX-001",
        category="weather_wind",
        result=CheckResult.CLEAR,
        observed=observed,
        threshold=threshold,
        source=weather.source,
        message="Sustained wind and gust are both within the operational ceiling.",
        assumptions=tuple(assumptions),
    )


def _check_precipitation(
    *, weather: WeatherRecord, aircraft: AircraftRecord
) -> CheckDetail:
    tolerance = aircraft.precipitation_tolerance_mm_h
    observed_rate = weather.precipitation_mm_h

    if tolerance is None or observed_rate is None:
        return CheckDetail(
            check_id="WX-002",
            category="weather_precipitation",
            result=CheckResult.UNAVAILABLE,
            observed={"precipitation_mm_h": observed_rate},
            threshold={"tolerance_mm_h": tolerance},
            source=weather.source,
            message="Precipitation could not be assessed.",
        )

    detail = {
        "observed": {"precipitation_mm_h": observed_rate},
        "threshold": {"tolerance_mm_h": tolerance},
    }

    if observed_rate > tolerance:
        return CheckDetail(
            check_id="WX-002",
            category="weather_precipitation",
            result=CheckResult.FAIL,
            source=weather.source,
            message=(
                f"Forecast precipitation of {observed_rate:.1f} mm/h exceeds the "
                f"airframe tolerance of {tolerance:.1f} mm/h."
            ),
            **detail,
        )

    return CheckDetail(
        check_id="WX-002",
        category="weather_precipitation",
        result=CheckResult.CLEAR,
        source=weather.source,
        message="No precipitation above tolerance for the planned window.",
        **detail,
    )


def _check_temperature(
    *, weather: WeatherRecord, aircraft: AircraftRecord
) -> CheckDetail:
    temperature = weather.temperature_c
    minimum = aircraft.operating_temp_min_c
    maximum = aircraft.operating_temp_max_c

    observed = {"temperature_c": temperature}
    threshold = {"operating_temp_min_c": minimum, "operating_temp_max_c": maximum}

    if temperature is None or minimum is None or maximum is None:
        return CheckDetail(
            check_id="WX-003",
            category="weather_temperature",
            result=CheckResult.UNAVAILABLE,
            observed=observed,
            threshold=threshold,
            source=weather.source,
            message="Temperature could not be assessed.",
        )

    if temperature < minimum or temperature > maximum:
        return CheckDetail(
            check_id="WX-003",
            category="weather_temperature",
            result=CheckResult.FAIL,
            observed=observed,
            threshold=threshold,
            source=weather.source,
            message=(
                f"Forecast temperature of {temperature:.1f} C is outside the "
                f"operating range {minimum:.1f} to {maximum:.1f} C."
            ),
        )

    return CheckDetail(
        check_id="WX-003",
        category="weather_temperature",
        result=CheckResult.CLEAR,
        observed=observed,
        threshold=threshold,
        source=weather.source,
        message="Forecast temperature is within the operating range.",
    )
