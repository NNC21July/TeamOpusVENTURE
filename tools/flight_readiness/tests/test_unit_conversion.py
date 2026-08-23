"""Unit conversion tests.

A conversion error is the most likely single bug capable of producing a false
GO, which is the dangerous failure direction. Hence its own file.
"""

import pytest

from tools.flight_readiness.sources.weather_normaliser import (
    build_weather_record,
    kmh_to_ms,
    knots_to_ms,
    ms_to_kmh,
)
from tools.flight_readiness.tests.fixtures.weather_responses import VALID_AT


def test_kmh_to_ms_known_values() -> None:
    assert kmh_to_ms(3.6) == pytest.approx(1.0)
    assert kmh_to_ms(36.0) == pytest.approx(10.0)
    assert kmh_to_ms(0.0) == pytest.approx(0.0)


def test_ms_to_kmh_known_values() -> None:
    assert ms_to_kmh(1.0) == pytest.approx(3.6)
    assert ms_to_kmh(10.0) == pytest.approx(36.0)


def test_round_trip_is_lossless() -> None:
    for value in (0.0, 1.0, 7.8, 12.0, 43.7):
        assert kmh_to_ms(ms_to_kmh(value)) == pytest.approx(value)


def test_none_stays_none() -> None:
    # Critical: a missing gust must not become 0.0, which would read as calm.
    assert kmh_to_ms(None) is None
    assert ms_to_kmh(None) is None
    assert knots_to_ms(None) is None


def test_conversion_direction_is_not_inverted() -> None:
    # The dangerous direction. If kmh_to_ms multiplied instead of divided,
    # a 30 km/h wind would read as 108 m/s (fails safe). If ms_to_kmh were
    # used where kmh_to_ms belongs, 30 km/h reads as 8.3 -> still over a
    # 7.8 ceiling. This pins the direction so neither can silently swap.
    assert kmh_to_ms(30.0) < 30.0
    assert ms_to_kmh(30.0) > 30.0


def test_ceiling_boundary_in_real_units() -> None:
    # A Matrice 4 ceiling is 7.8 m/s = 28.08 km/h. A source reporting 30 km/h
    # must land above the ceiling once converted.
    assert kmh_to_ms(30.0) > 7.8
    assert kmh_to_ms(28.0) < 7.8


def test_knots_conversion() -> None:
    assert knots_to_ms(1.0) == pytest.approx(0.514444)


def test_build_weather_record_converts_wind_only() -> None:
    record = build_weather_record(
        source="open-meteo",
        valid_at=VALID_AT,
        wind_sustained_kmh=36.0,
        wind_gust_kmh=54.0,
        wind_altitude_m=60.0,
        precipitation_mm_h=1.2,
        temperature_c=29.0,
    )
    assert record.wind_sustained_ms == pytest.approx(10.0)
    assert record.wind_gust_ms == pytest.approx(15.0)
    # Precipitation and temperature are already in target units: untouched.
    assert record.precipitation_mm_h == pytest.approx(1.2)
    assert record.temperature_c == pytest.approx(29.0)
    assert record.wind_altitude_m == pytest.approx(60.0)


def test_build_weather_record_preserves_missing_gust() -> None:
    record = build_weather_record(
        source="nea", valid_at=VALID_AT, wind_sustained_kmh=21.6, wind_gust_kmh=None
    )
    assert record.wind_sustained_ms == pytest.approx(6.0)
    assert record.wind_gust_ms is None
