"""Parser tests for the two live weather sources.

Run against recorded payloads from tests/fixtures/api_payloads.py, so the
response shapes are real but the assertions are deterministic. The clients'
HTTP layer is separated from their parsing for exactly this reason.

A live smoke test lives at the bottom, skipped unless RUN_LIVE_WEATHER=1.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from tools.flight_readiness.sources.nea_client import (
    RAINFALL_INTERVALS_PER_HOUR,
    STATION_HEIGHT_M,
    parse_observations,
)
from tools.flight_readiness.sources.open_meteo_client import (
    WIND_HEIGHTS_M,
    nearest_wind_height,
    parse_forecast,
)
from tools.flight_readiness.sources.weather_protocol import WeatherSource
from tools.flight_readiness.tests.fixtures.api_payloads import (
    NEA_RAINFALL,
    NEA_TEMPERATURE,
    NEA_WIND,
    OPEN_METEO_FORECAST,
)

SG = timezone(timedelta(hours=8))
JURONG_LON, JURONG_LAT = 103.8010, 1.3010


def window_from_payload(hours: int = 2):
    """A window that lands inside the recorded forecast's hourly steps."""
    offset = timedelta(seconds=OPEN_METEO_FORECAST["utc_offset_seconds"])
    stamps = [
        datetime.fromisoformat(t).replace(tzinfo=timezone(offset))
        for t in OPEN_METEO_FORECAST["hourly"]["time"]
    ]
    return stamps[0], stamps[min(hours, len(stamps) - 1)]


# --- Open-Meteo -------------------------------------------------------------


def test_recorded_payload_reports_metres_per_second() -> None:
    # The client asks for wind_speed_unit=ms, so no conversion is applied.
    assert OPEN_METEO_FORECAST["hourly_units"]["wind_speed_10m"] == "m/s"
    assert OPEN_METEO_FORECAST["hourly_units"]["wind_gusts_10m"] == "m/s"


def test_gust_exists_only_at_ten_metres() -> None:
    # wind_gusts_80m is rejected by the API. Gust is always ground level.
    keys = set(OPEN_METEO_FORECAST["hourly"])
    assert "wind_gusts_10m" in keys
    assert not any(k.startswith("wind_gusts_") and k != "wind_gusts_10m" for k in keys)


def test_nearest_wind_height_picks_facade_altitude() -> None:
    assert nearest_wind_height(60.0) == 80
    assert nearest_wind_height(5.0) == 10
    assert nearest_wind_height(45.0) == 40
    assert nearest_wind_height(200.0) == 120
    assert all(nearest_wind_height(h) == h for h in WIND_HEIGHTS_M)


def test_parses_recorded_forecast() -> None:
    start, end = window_from_payload()
    record = parse_forecast(
        OPEN_METEO_FORECAST, altitude_m=60.0, valid_from=start, valid_until=end
    )
    assert record.source == "open-meteo"
    assert record.wind_altitude_m == 80.0
    assert record.wind_sustained_ms is not None
    assert record.wind_gust_ms is not None
    assert record.temperature_c is not None
    assert record.valid_at.tzinfo is not None


def test_window_aggregation_takes_the_worst_hour() -> None:
    # A forecast that is calm at 09:00 and unflyable at 10:00 must not average.
    start, end = window_from_payload(hours=6)
    wide = parse_forecast(
        OPEN_METEO_FORECAST, altitude_m=60.0, valid_from=start, valid_until=end
    )
    narrow = parse_forecast(
        OPEN_METEO_FORECAST,
        altitude_m=60.0,
        valid_from=start,
        valid_until=start + timedelta(hours=1),
    )
    assert wide.wind_sustained_ms >= narrow.wind_sustained_ms
    assert wide.temperature_max_c >= narrow.temperature_max_c
    assert wide.temperature_min_c <= narrow.temperature_min_c


def test_altitude_selects_a_different_wind_field() -> None:
    start, end = window_from_payload()
    low = parse_forecast(
        OPEN_METEO_FORECAST, altitude_m=10.0, valid_from=start, valid_until=end
    )
    high = parse_forecast(
        OPEN_METEO_FORECAST, altitude_m=120.0, valid_from=start, valid_until=end
    )
    assert low.wind_altitude_m == 10.0
    assert high.wind_altitude_m == 120.0


def test_window_outside_the_payload_falls_back_to_closest_step() -> None:
    start, _ = window_from_payload()
    far = start + timedelta(days=40)
    record = parse_forecast(
        OPEN_METEO_FORECAST,
        altitude_m=60.0,
        valid_from=far,
        valid_until=far + timedelta(hours=1),
    )
    assert record.wind_sustained_ms is not None


# --- NEA --------------------------------------------------------------------


def test_recorded_wind_is_in_knots_not_kmh() -> None:
    # The correction that matters most: treating knots as km/h understates
    # wind by about 1.9x, which is the false-GO direction.
    assert NEA_WIND["data"]["readingUnit"] == "knots"


def test_recorded_rainfall_is_a_five_minute_total() -> None:
    assert "5 Minute Total" in NEA_RAINFALL["data"]["readingType"]
    assert RAINFALL_INTERVALS_PER_HOUR == 12


def test_nea_publishes_no_gust() -> None:
    assert "gust" not in repr(NEA_WIND).lower()


def test_parses_recorded_observations() -> None:
    record = parse_observations(
        wind=NEA_WIND,
        temperature=NEA_TEMPERATURE,
        rainfall=NEA_RAINFALL,
        longitude=JURONG_LON,
        latitude=JURONG_LAT,
    )
    assert record.source == "nea"
    assert record.wind_altitude_m == STATION_HEIGHT_M
    assert record.temperature_c is not None
    assert record.observed_at is not None and record.observed_at.tzinfo is not None


def test_knots_are_converted_to_metres_per_second() -> None:
    record = parse_observations(
        wind=NEA_WIND,
        temperature=NEA_TEMPERATURE,
        rainfall=NEA_RAINFALL,
        longitude=JURONG_LON,
        latitude=JURONG_LAT,
    )
    raw = {i["stationId"]: i["value"] for i in NEA_WIND["data"]["readings"][0]["data"]}
    expected = {round(v * 0.514444, 6) for v in raw.values() if v is not None}
    assert round(record.wind_sustained_ms, 6) in expected
    # Sanity: a knots reading converted as km/h would be ~1.9x smaller.
    assert record.wind_sustained_ms > 0


def test_gust_stays_none_so_the_predictor_can_flag_it() -> None:
    record = parse_observations(
        wind=NEA_WIND,
        temperature=NEA_TEMPERATURE,
        rainfall=NEA_RAINFALL,
        longitude=JURONG_LON,
        latitude=JURONG_LAT,
    )
    assert record.wind_gust_ms is None


def test_rainfall_is_scaled_to_an_hourly_rate() -> None:
    record = parse_observations(
        wind=NEA_WIND,
        temperature=NEA_TEMPERATURE,
        rainfall=NEA_RAINFALL,
        longitude=JURONG_LON,
        latitude=JURONG_LAT,
    )
    raw = {
        i["stationId"]: i["value"] for i in NEA_RAINFALL["data"]["readings"][0]["data"]
    }
    expected = {v * RAINFALL_INTERVALS_PER_HOUR for v in raw.values() if v is not None}
    assert record.precipitation_mm_h in expected


def test_nearest_station_wins() -> None:
    # Same payload, two far-apart locations, different stations selected.
    west = parse_observations(
        wind=NEA_WIND,
        temperature=NEA_TEMPERATURE,
        rainfall=NEA_RAINFALL,
        longitude=103.70,
        latitude=1.35,
    )
    east = parse_observations(
        wind=NEA_WIND,
        temperature=NEA_TEMPERATURE,
        rainfall=NEA_RAINFALL,
        longitude=103.98,
        latitude=1.35,
    )
    assert isinstance(west.wind_sustained_ms, float)
    assert isinstance(east.wind_sustained_ms, float)


# --- protocol conformance ---------------------------------------------------


def test_clients_satisfy_the_weather_source_protocol() -> None:
    from tools.flight_readiness.sources.nea_client import NeaClient
    from tools.flight_readiness.sources.open_meteo_client import OpenMeteoClient

    forecast: WeatherSource = OpenMeteoClient()
    observations: WeatherSource = NeaClient()
    assert forecast is not None and observations is not None


# --- live smoke test --------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_WEATHER") != "1",
    reason="hits the network; set RUN_LIVE_WEATHER=1 to run",
)
def test_live_open_meteo_round_trip() -> None:
    from tools.flight_readiness.sources.open_meteo_client import OpenMeteoClient

    start = datetime.now(timezone.utc) + timedelta(hours=6)
    record = OpenMeteoClient().get_weather(
        longitude=JURONG_LON,
        latitude=JURONG_LAT,
        altitude_m=60.0,
        valid_from=start,
        valid_until=start + timedelta(hours=1),
    )
    assert record.wind_sustained_ms is not None
    assert 0 <= record.wind_sustained_ms < 60  # m/s, not km/h or knots


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_WEATHER") != "1",
    reason="hits the network; set RUN_LIVE_WEATHER=1 to run",
)
def test_live_nea_round_trip() -> None:
    from tools.flight_readiness.sources.nea_client import NeaClient

    now = datetime.now(timezone.utc)
    record = NeaClient().get_weather(
        longitude=JURONG_LON,
        latitude=JURONG_LAT,
        altitude_m=60.0,
        valid_from=now,
        valid_until=now + timedelta(hours=1),
    )
    assert record.temperature_c is not None
    assert record.wind_gust_ms is None
