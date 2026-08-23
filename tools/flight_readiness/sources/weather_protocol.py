from datetime import datetime
from typing import Protocol

from tools.flight_readiness.request_response_schemas import WeatherRecord


class WeatherDataUnavailableError(RuntimeError):
    """Raised when weather cannot be retrieved for the requested window"""


class ForecastHorizonExceededError(RuntimeError):
    """Raised when the requested window is beyond what the source can forecast.

    Distinct from unavailability: the input was valid, the capability was not.
    """


class WeatherSource(Protocol):
    # Weather capability required by the weather predictor. Implemented by both
    # the Open-Meteo and NEA clients, which normalise to m/s and degrees C before
    # returning, so the predictor does not care which source answered.
    def get_weather(
        self,
        *,
        longitude: float,
        latitude: float,
        altitude_m: float,
        valid_from: datetime,
        valid_until: datetime,
    ) -> WeatherRecord:
        ...
