"""Open-Meteo forecast source.

Primary forecast source: 16-day horizon, native gust, and native wind at
multiple heights. No API key, no signup, CC BY 4.0.

Verified against the live API:

  * gust variable is `wind_gusts_10m`; there is NO gust at altitude —
    `wind_gusts_80m` is rejected outright. Gust is therefore always a
    ground-level figure, which is recorded on the returned record.
  * `wind_speed_unit=ms` returns m/s natively, so no conversion is applied
    here. The normaliser is still used by NEA, which reports knots.
  * the GEM model exposes wind_speed at 10 m, 40 m, 80 m and 120 m.
  * `forecast_days=16` returns 384 hourly steps.

Values are aggregated across the mission window conservatively: the worst
wind, worst gust, worst precipitation, and both temperature extremes. A
forecast that is fine at 09:00 and unflyable at 10:00 must not average out.
"""

from datetime import datetime, timedelta, timezone

import httpx

from tools.flight_readiness.request_response_schemas import WeatherRecord
from tools.flight_readiness.sources.weather_protocol import (
    ForecastHorizonExceededError,
    WeatherDataUnavailableError,
)
from tools.flight_readiness.specs.thresholds import OPEN_METEO_FORECAST_HORIZON_DAYS

BASE_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE_NAME = "open-meteo"

# Heights the GEM model publishes wind at. Gust is 10 m only.
WIND_HEIGHTS_M = (10, 40, 80, 120)
GUST_HEIGHT_M = 10

_HOURLY_VARIABLES = (
    tuple(f"wind_speed_{h}m" for h in WIND_HEIGHTS_M)
    + ("wind_gusts_10m", "precipitation", "temperature_2m")
)


class OpenMeteoClient:
    """Satisfies the WeatherSource protocol against the live Open-Meteo API."""

    def __init__(
        self,
        *,
        model: str = "gem_seamless",
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
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
        horizon = datetime.now(timezone.utc) + timedelta(
            days=OPEN_METEO_FORECAST_HORIZON_DAYS
        )
        if valid_from > horizon:
            raise ForecastHorizonExceededError(
                f"Open-Meteo forecasts at most "
                f"{OPEN_METEO_FORECAST_HORIZON_DAYS} days ahead."
            )

        payload = self._fetch(
            longitude=longitude, latitude=latitude, valid_from=valid_from
        )
        return parse_forecast(
            payload,
            altitude_m=altitude_m,
            valid_from=valid_from,
            valid_until=valid_until,
        )

    def _fetch(
        self, *, longitude: float, latitude: float, valid_from: datetime
    ) -> dict:
        lead_days = (valid_from - datetime.now(timezone.utc)).days + 2
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(_HOURLY_VARIABLES),
            "wind_speed_unit": "ms",
            "models": self._model,
            "forecast_days": max(1, min(lead_days, OPEN_METEO_FORECAST_HORIZON_DAYS)),
            "timezone": "UTC",
        }
        try:
            if self._client is not None:
                response = self._client.get(BASE_URL, params=params)
            else:
                response = httpx.get(BASE_URL, params=params, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise WeatherDataUnavailableError(
                f"Open-Meteo request failed: {exc}"
            ) from exc
        except ValueError as exc:
            raise WeatherDataUnavailableError(
                "Open-Meteo returned a response that was not JSON"
            ) from exc


def nearest_wind_height(altitude_m: float) -> int:
    """The published height closest to the planned altitude.

    Facade inspection at 60 m maps to the 80 m field rather than 10 m, which
    is the whole reason for preferring a model with native multi-height wind.

    Ties break upward. A 60 m mission is equidistant from the 40 m and 80 m
    fields, and wind strengthens with height — so taking the lower field would
    understate conditions at the planned altitude, which is the direction that
    produces a false GO.
    """
    return min(
        WIND_HEIGHTS_M, key=lambda height: (abs(height - altitude_m), -height)
    )


def parse_forecast(
    payload: dict,
    *,
    altitude_m: float,
    valid_from: datetime,
    valid_until: datetime,
) -> WeatherRecord:
    """Turn an Open-Meteo response into one normalised record for the window.

    Split out from the HTTP call so it can be tested against a recorded
    payload without touching the network.
    """
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        raise WeatherDataUnavailableError("Open-Meteo returned no hourly data")

    offset = timedelta(seconds=payload.get("utc_offset_seconds", 0))
    stamps = [_parse_time(value, offset) for value in times]

    indices = [
        i for i, stamp in enumerate(stamps) if valid_from <= stamp <= valid_until
    ]
    if not indices:
        # The window may fall between hourly steps, or sit at the very edge of
        # the range. Fall back to the single closest step rather than failing.
        indices = [min(range(len(stamps)), key=lambda i: abs(stamps[i] - valid_from))]

    height = nearest_wind_height(altitude_m)
    sustained = _worst(hourly.get(f"wind_speed_{height}m"), indices, max)
    gust = _worst(hourly.get("wind_gusts_10m"), indices, max)
    precipitation = _worst(hourly.get("precipitation"), indices, max)
    temp_max = _worst(hourly.get("temperature_2m"), indices, max)
    temp_min = _worst(hourly.get("temperature_2m"), indices, min)

    return WeatherRecord(
        source=SOURCE_NAME,
        valid_at=stamps[indices[0]],
        wind_sustained_ms=sustained,
        wind_gust_ms=gust,
        wind_altitude_m=float(height),
        # Hourly precipitation totals in mm are already an mm/h rate.
        precipitation_mm_h=precipitation,
        temperature_c=temp_max,
        temperature_min_c=temp_min,
        temperature_max_c=temp_max,
        observed_at=datetime.now(timezone.utc),
    )


def _parse_time(value: str, offset: timedelta) -> datetime:
    # Open-Meteo omits the offset from hourly timestamps and reports it once,
    # at the top level, so it has to be reattached here.
    return datetime.fromisoformat(value).replace(tzinfo=timezone(offset))


def _worst(series, indices, chooser):
    if not series:
        return None
    values = [
        series[i] for i in indices if i < len(series) and series[i] is not None
    ]
    return chooser(values) if values else None
