"""Normalised weather records for predictor tests.

Values are already in m/s and degrees C, as a source client would return them.
Calibrated against a Matrice 4: rated max wind 12.0 m/s, so with a derating
factor of 0.65 the operational ceiling is 7.8 m/s and the warning band opens
at 0.85 x 7.8 = 6.63 m/s.
"""

from datetime import datetime, timedelta, timezone

from tools.flight_readiness.request_response_schemas import WeatherRecord

SG_TIMEZONE = timezone(timedelta(hours=8))

VALID_AT = datetime(2026, 8, 25, 9, 0, tzinfo=SG_TIMEZONE)


CALM = WeatherRecord(
    source="open-meteo",
    valid_at=VALID_AT,
    wind_sustained_ms=3.0,
    wind_gust_ms=4.2,
    wind_altitude_m=60.0,
    precipitation_mm_h=0.0,
    temperature_c=29.0,
    observed_at=VALID_AT,
)

# Gust 7.4 sits between the warning band (6.63) and the ceiling (7.8).
GUST_IN_WARNING_BAND = WeatherRecord(
    source="open-meteo",
    valid_at=VALID_AT,
    wind_sustained_ms=6.1,
    wind_gust_ms=7.4,
    wind_altitude_m=60.0,
    precipitation_mm_h=0.0,
    temperature_c=29.0,
    observed_at=VALID_AT,
)

SUSTAINED_ABOVE_CEILING = WeatherRecord(
    source="open-meteo",
    valid_at=VALID_AT,
    wind_sustained_ms=9.0,
    wind_gust_ms=11.0,
    wind_altitude_m=60.0,
    precipitation_mm_h=0.0,
    temperature_c=29.0,
    observed_at=VALID_AT,
)

# The case that a sustained-wind-only check would wrongly clear.
GUST_ABOVE_CEILING_SUSTAINED_BELOW = WeatherRecord(
    source="open-meteo",
    valid_at=VALID_AT,
    wind_sustained_ms=5.0,
    wind_gust_ms=8.5,
    wind_altitude_m=60.0,
    precipitation_mm_h=0.0,
    temperature_c=29.0,
    observed_at=VALID_AT,
)

PRECIPITATION_PRESENT = WeatherRecord(
    source="open-meteo",
    valid_at=VALID_AT,
    wind_sustained_ms=3.0,
    wind_gust_ms=4.2,
    wind_altitude_m=60.0,
    precipitation_mm_h=2.4,
    temperature_c=27.0,
    observed_at=VALID_AT,
)

TEMPERATURE_TOO_HOT = WeatherRecord(
    source="nea",
    valid_at=VALID_AT,
    wind_sustained_ms=3.0,
    wind_gust_ms=4.2,
    wind_altitude_m=60.0,
    precipitation_mm_h=0.0,
    temperature_c=44.0,
    observed_at=VALID_AT,
)

TEMPERATURE_TOO_COLD = WeatherRecord(
    source="nea",
    valid_at=VALID_AT,
    wind_sustained_ms=3.0,
    wind_gust_ms=4.2,
    wind_altitude_m=60.0,
    precipitation_mm_h=0.0,
    temperature_c=-15.0,
    observed_at=VALID_AT,
)

# Source answered but omitted gust. Gust is the dominant wind risk, so this
# must not be silently treated as "no gust".
GUST_MISSING = WeatherRecord(
    source="nea",
    valid_at=VALID_AT,
    wind_sustained_ms=6.0,
    wind_gust_ms=None,
    wind_altitude_m=10.0,
    precipitation_mm_h=0.0,
    temperature_c=29.0,
    observed_at=VALID_AT,
)

# Stale beyond the NEA 15-minute policy.
STALE_OBSERVATION = WeatherRecord(
    source="nea",
    valid_at=VALID_AT,
    wind_sustained_ms=3.0,
    wind_gust_ms=4.2,
    wind_altitude_m=10.0,
    precipitation_mm_h=0.0,
    temperature_c=29.0,
    observed_at=VALID_AT - timedelta(hours=3),
)
