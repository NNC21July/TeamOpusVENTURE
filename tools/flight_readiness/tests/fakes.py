from datetime import datetime

from tools.flight_readiness.client_protocol import (
    AircraftDataUnavailableError,
    DroneNotFoundError,
    MaintenanceDataUnavailableError,
)
from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    BatteryRecord,
    MaintenanceSnapshot,
    WeatherRecord,
)
from tools.flight_readiness.sources.weather_protocol import (
    ForecastHorizonExceededError,
    WeatherDataUnavailableError,
)


class FakeAircraftClient:
    def __init__(
        self,
        aircraft: AircraftRecord | None = None,
        battery: BatteryRecord | None = None,
        *,
        unavailable: bool = False,
        not_found: bool = False,
    ) -> None:
        self._aircraft = aircraft
        self._battery = battery
        self._unavailable = unavailable
        self._not_found = not_found
        self.aircraft_queries: list[str] = []
        self.battery_queries: list[str] = []

    def get_aircraft(self, *, drone: str) -> AircraftRecord:
        # Return the prepared aircraft record, or simulate a failure mode
        self.aircraft_queries.append(drone)

        if self._not_found:
            raise DroneNotFoundError(f"Fake client does not know drone {drone}")
        if self._unavailable or self._aircraft is None:
            raise AircraftDataUnavailableError("Fake aircraft data is unavailable")

        return self._aircraft

    def get_battery(self, *, drone_id: str) -> BatteryRecord:
        # Return the prepared battery record, or simulate unavailable data
        self.battery_queries.append(drone_id)

        if self._unavailable or self._battery is None:
            raise AircraftDataUnavailableError("Fake battery data is unavailable")

        return self._battery


class FakeMaintenanceReader:
    def __init__(
        self,
        snapshot: MaintenanceSnapshot | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        self._snapshot = snapshot
        self._unavailable = unavailable
        self.queries: list[str] = []

    def get_maintenance_status(self, *, drone_id: str) -> MaintenanceSnapshot:
        # Return the prepared maintenance snapshot, or simulate unavailable data
        self.queries.append(drone_id)

        if self._unavailable or self._snapshot is None:
            raise MaintenanceDataUnavailableError("Fake maintenance data is unavailable")

        return self._snapshot


class FakeWeatherSource:
    def __init__(
        self,
        weather: WeatherRecord | None = None,
        *,
        unavailable: bool = False,
        beyond_horizon: bool = False,
    ) -> None:
        self._weather = weather
        self._unavailable = unavailable
        self._beyond_horizon = beyond_horizon
        self.queries: list[tuple[float, float, float, datetime, datetime]] = []

    def get_weather(
        self,
        *,
        longitude: float,
        latitude: float,
        altitude_m: float,
        valid_from: datetime,
        valid_until: datetime,
    ) -> WeatherRecord:
        # Return the prepared weather record, or simulate a failure mode
        self.queries.append((longitude, latitude, altitude_m, valid_from, valid_until))

        if self._beyond_horizon:
            raise ForecastHorizonExceededError(
                "Fake weather source cannot forecast this far ahead"
            )
        if self._unavailable or self._weather is None:
            raise WeatherDataUnavailableError("Fake weather data is unavailable")

        return self._weather
