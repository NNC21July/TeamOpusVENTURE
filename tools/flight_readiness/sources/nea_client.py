"""NEA realtime observation source, via data.gov.sg.

Ground truth for the under-two-hours path: authoritative local station
observations at 1-minute resolution. Not a forecast source — these endpoints
report only what is happening now.

Verified against the live API, correcting three things assumed in Research 2:

  * NO API KEY is required. The v2 endpoints are open.
  * WIND IS IN KNOTS, not km/h. `readingUnit: "knots"`. Treating a knots
    figure as km/h understates wind by about 1.9x, which is the false-GO
    direction, so this is the most important correction in the file.
  * RAINFALL IS A 5-MINUTE TOTAL in mm, not a rate. Multiplied by 12 here to
    reach mm/h.

Confirmed as the document expected: there is no gust field anywhere in the
wind-speed response, which is why Open-Meteo remains the primary source.
Readings are station-level, so the nearest station to the mission location is
selected per variable — the station sets differ between endpoints (17 for
wind, 18 for temperature, 90 for rainfall).
"""

import math
from datetime import datetime, timedelta, timezone

import httpx

from tools.flight_readiness.request_response_schemas import WeatherRecord
from tools.flight_readiness.sources.weather_normaliser import knots_to_ms
from tools.flight_readiness.sources.weather_protocol import (
    ForecastHorizonExceededError,
    WeatherDataUnavailableError,
)
from tools.flight_readiness.specs.thresholds import (
    LIVE_OBSERVATION_HORIZON_HOURS,
    NEA_OBSERVATION_MAX_AGE_MINUTES,
)

BASE_URL = "https://api-open.data.gov.sg/v2/real-time/api"
SOURCE_NAME = "nea"

# NEA measures at station height, roughly 10 m above ground.
STATION_HEIGHT_M = 10.0

# Rainfall is published as a 5-minute accumulation; twelve of those per hour.
RAINFALL_INTERVALS_PER_HOUR = 12


class NeaClient:
    """Satisfies the WeatherSource protocol against live NEA observations."""

    def __init__(
        self, *, timeout: float = 20.0, client: httpx.Client | None = None
    ) -> None:
        self._timeout = timeout
        self._client = client

    def get_weather(
        self,
        *,
        longitude: float,
        latitude: float,
        altitude_m: float,
        valid_from: datetime,
        valid_until: datetime,
    ) -> WeatherRecord:
        # These endpoints report now. Asking them about next Tuesday is a
        # capability limit, not a failure.
        lead = valid_from - datetime.now(timezone.utc)
        if lead > timedelta(hours=LIVE_OBSERVATION_HORIZON_HOURS):
            raise ForecastHorizonExceededError(
                "NEA realtime observations cover current conditions only."
            )

        wind = self._fetch("wind-speed")
        temperature = self._fetch("air-temperature")
        rainfall = self._fetch("rainfall")

        return parse_observations(
            wind=wind,
            temperature=temperature,
            rainfall=rainfall,
            longitude=longitude,
            latitude=latitude,
        )

    def _fetch(self, endpoint: str) -> dict:
        url = f"{BASE_URL}/{endpoint}"
        try:
            if self._client is not None:
                response = self._client.get(url)
            else:
                response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise WeatherDataUnavailableError(
                f"NEA {endpoint} request failed: {exc}"
            ) from exc
        except ValueError as exc:
            raise WeatherDataUnavailableError(
                f"NEA {endpoint} returned a response that was not JSON"
            ) from exc


def parse_observations(
    *,
    wind: dict,
    temperature: dict,
    rainfall: dict,
    longitude: float,
    latitude: float,
) -> WeatherRecord:
    """Build one normalised record from three NEA endpoint payloads.

    Split from the HTTP calls so it can be tested against recorded payloads.
    """
    wind_knots, wind_time = _nearest_reading(wind, longitude, latitude)
    temp_c, _ = _nearest_reading(temperature, longitude, latitude)
    rain_mm_5min, _ = _nearest_reading(rainfall, longitude, latitude)

    if wind_knots is None and temp_c is None and rain_mm_5min is None:
        raise WeatherDataUnavailableError("NEA returned no usable station readings")

    rain_mm_h = (
        rain_mm_5min * RAINFALL_INTERVALS_PER_HOUR if rain_mm_5min is not None else None
    )

    return WeatherRecord(
        source=SOURCE_NAME,
        valid_at=wind_time or datetime.now(timezone.utc),
        wind_sustained_ms=knots_to_ms(wind_knots),
        # NEA publishes no gust figure. Left as None deliberately: the weather
        # predictor caps a gustless assessment at WARNING rather than clearing.
        wind_gust_ms=None,
        wind_altitude_m=STATION_HEIGHT_M,
        precipitation_mm_h=rain_mm_h,
        temperature_c=temp_c,
        temperature_min_c=temp_c,
        temperature_max_c=temp_c,
        observed_at=wind_time or datetime.now(timezone.utc),
    )


def is_stale(record: WeatherRecord, *, now: datetime) -> bool:
    """True when an observation is older than the staleness policy allows."""
    if record.observed_at is None:
        return True
    return now - record.observed_at > timedelta(
        minutes=NEA_OBSERVATION_MAX_AGE_MINUTES
    )


def _nearest_reading(
    payload: dict, longitude: float, latitude: float
) -> tuple[float | None, datetime | None]:
    data = payload.get("data") or {}
    stations = data.get("stations") or []
    readings = data.get("readings") or []
    if not stations or not readings:
        return None, None

    latest = readings[0]
    values = {
        item.get("stationId"): item.get("value") for item in latest.get("data") or []
    }

    # Only stations that actually reported this cycle are candidates; the
    # closest station is useless if it returned nothing.
    reporting = [
        station
        for station in stations
        if values.get(station.get("id")) is not None
        and station.get("location")
    ]
    if not reporting:
        return None, None

    closest = min(
        reporting,
        key=lambda station: _distance_km(
            longitude,
            latitude,
            station["location"]["longitude"],
            station["location"]["latitude"],
        ),
    )

    timestamp = latest.get("timestamp")
    parsed = datetime.fromisoformat(timestamp) if timestamp else None
    return values.get(closest.get("id")), parsed


def _distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance. Singapore is small, but stations are ranked by it."""
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))
