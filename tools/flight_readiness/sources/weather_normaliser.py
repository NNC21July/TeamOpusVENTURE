"""Unit conversion and record construction for weather sources.

Both NEA and Open-Meteo report wind in km/h by default, while every aircraft
limit is in m/s. Converting in one place, at ingestion, means the predictors
never see a raw source value and cannot compare mismatched units.

This is the highest-risk file in the tool for its size. A missing divisor turns
30 km/h (8.3 m/s, over a Matrice 4's 7.8 m/s ceiling) into "30 m/s" — which
fails safe — but the inverse, treating m/s as km/h, turns 12 m/s into 3.3 m/s
and produces a false GO. Hence the dedicated test file.
"""

from datetime import datetime

from tools.flight_readiness.request_response_schemas import WeatherRecord

# 1 m/s = 3.6 km/h exactly.
_KMH_PER_MS = 3.6


def kmh_to_ms(value: float | None) -> float | None:
    """Convert km/h to m/s. None passes through as None, never as zero."""
    if value is None:
        return None
    return value / _KMH_PER_MS


def ms_to_kmh(value: float | None) -> float | None:
    """Convert m/s to km/h. Present for symmetry and round-trip testing."""
    if value is None:
        return None
    return value * _KMH_PER_MS


def knots_to_ms(value: float | None) -> float | None:
    """Convert knots to m/s, in case a source reports marine units."""
    if value is None:
        return None
    return value * 0.514444


def build_weather_record(
    *,
    source: str,
    valid_at: datetime,
    wind_sustained_kmh: float | None = None,
    wind_gust_kmh: float | None = None,
    wind_altitude_m: float | None = None,
    precipitation_mm_h: float | None = None,
    temperature_c: float | None = None,
    observed_at: datetime | None = None,
) -> WeatherRecord:
    """Build a normalised record from km/h + degrees C source values.

    Parameter names carry their units so a caller cannot pass m/s to a field
    that is about to be divided by 3.6 without it being obvious at the call site.
    """
    return WeatherRecord(
        source=source,
        valid_at=valid_at,
        wind_sustained_ms=kmh_to_ms(wind_sustained_kmh),
        wind_gust_ms=kmh_to_ms(wind_gust_kmh),
        wind_altitude_m=wind_altitude_m,
        precipitation_mm_h=precipitation_mm_h,
        temperature_c=temperature_c,
        observed_at=observed_at or valid_at,
    )
