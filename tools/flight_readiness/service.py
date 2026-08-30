"""check_flight_readiness — orchestration.

The only module here that touches the outside world, and it does so entirely
through injected protocols, so the whole tool is testable with fakes.

    validate -> select source -> fetch -> run predictors -> aggregate -> shape

Predictors run to completion regardless of each other's outcome. If the weather
source is down, endurance and airworthiness are still assessed, so a pilot sees
every failing factor in one call rather than one per call.
"""

from dataclasses import replace
from datetime import datetime

from tools.flight_readiness.aggregation import (
    aggregate_decision,
    apply_confidence,
    collect_assumptions,
    collect_blocking_factors,
    collect_warnings,
    derive_confidence,
)
from tools.flight_readiness.client_protocol import (
    AircraftClient,
    AircraftDataUnavailableError,
    DroneNotFoundError,
    MaintenanceDataUnavailableError,
    MaintenanceReader,
)
from tools.flight_readiness.decision_types import CheckResult, OverallDecision
from tools.flight_readiness.input_validation import (
    exceeds_forecast_horizon,
    validate_request,
)
from tools.flight_readiness.predictors.airworthiness_predictor import (
    check_airworthiness,
)
from tools.flight_readiness.predictors.endurance_predictor import check_endurance
from tools.flight_readiness.predictors.weather_predictor import check_weather
from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    BatteryRecord,
    CheckDetail,
    FlightReadinessRequest,
    FlightReadinessResponse,
    MaintenanceSnapshot,
    WeatherRecord,
)
from tools.flight_readiness.sources.weather_protocol import (
    ForecastHorizonExceededError,
    WeatherDataUnavailableError,
    WeatherSource,
)
from tools.flight_readiness.specs.thresholds import LIVE_OBSERVATION_HORIZON_HOURS


def check_flight_readiness(
    *,
    request: FlightReadinessRequest,
    aircraft_client: AircraftClient,
    maintenance_reader: MaintenanceReader,
    forecast_source: WeatherSource,
    observation_source: WeatherSource | None = None,
    now: datetime,
) -> FlightReadinessResponse:
    validation = validate_request(request, now=now)
    if not validation.is_valid:
        return FlightReadinessResponse(
            decision=OverallDecision.NEEDS_INFO,
            missing_inputs=validation.errors,
            recommended_actions=("Correct the request and try again",),
            data_checked_at=now,
        )

    if exceeds_forecast_horizon(request, now=now):
        return FlightReadinessResponse(
            decision=OverallDecision.UNKNOWN,
            checks=(
                CheckDetail(
                    check_id="WX-001",
                    category="weather_wind",
                    result=CheckResult.UNAVAILABLE,
                    message="Planned start is beyond the available forecast range.",
                ),
            ),
            warnings=("Planned start is beyond the available forecast range.",),
            recommended_actions=(
                "Re-run this check once the flight is within the forecast horizon",
            ),
            data_checked_at=now,
        )

    aircraft, aircraft_error = _fetch_aircraft(aircraft_client, request.drone)
    if isinstance(aircraft_error, DroneNotFoundError):
        return FlightReadinessResponse(
            decision=OverallDecision.NEEDS_INFO,
            missing_inputs=(f"Drone {request.drone!r} could not be resolved",),
            recommended_actions=("Check the drone name or serial and try again",),
            data_checked_at=now,
        )

    battery = _fetch_battery(aircraft_client, aircraft)
    battery, battery_assumptions = _apply_pilot_battery(battery, request, now=now)
    maintenance = _fetch_maintenance(maintenance_reader, aircraft)

    duration, duration_derived = _mission_duration(request)

    # Without the airframe there are no limits to compare weather against, so
    # fetching a forecast we would only discard just adds latency.
    weather = None
    if aircraft is not None:
        source = _select_weather_source(
            request=request,
            now=now,
            forecast_source=forecast_source,
            observation_source=observation_source,
        )
        weather = _fetch_weather(source, request)

    checks = _run_predictors(
        aircraft=aircraft,
        battery=battery,
        maintenance=maintenance,
        weather=weather,
        duration=duration,
    )

    confidence = derive_confidence(
        now=now,
        planned_start_time=request.planned_start_time,
        checks=checks,
        aircraft=aircraft,
        battery=battery,
        maintenance=maintenance,
        weather=weather,
        mission_duration_derived=duration_derived,
    )

    decision = apply_confidence(aggregate_decision(checks), confidence)

    recommended: list[str] = []
    if confidence.recommended_recheck is not None:
        recommended.append(
            f"Re-run this check closer to the flight "
            f"({confidence.recommended_recheck.isoformat()})."
        )
    if decision is OverallDecision.NO_GO:
        recommended.append("Do not proceed to reserve airspace for this window.")

    return FlightReadinessResponse(
        decision=decision,
        confidence=confidence,
        checks=checks,
        blocking_factors=collect_blocking_factors(checks),
        warnings=collect_warnings(checks),
        assumptions=battery_assumptions + collect_assumptions(checks),
        recommended_actions=tuple(recommended),
        data_checked_at=now,
    )


def _run_predictors(
    *,
    aircraft: AircraftRecord | None,
    battery: BatteryRecord | None,
    maintenance: MaintenanceSnapshot | None,
    weather: WeatherRecord | None,
    duration: float | None,
) -> tuple[CheckDetail, ...]:
    if aircraft is None:
        # Without the airframe there are no limits to compare anything against.
        # Each message says what is missing for that specific factor rather
        # than repeating "Aircraft Service was unavailable" six times, which
        # reads as though the weather source itself had failed.
        return tuple(
            CheckDetail(
                check_id=check_id,
                category=category,
                result=CheckResult.UNAVAILABLE,
                message=message,
            )
            for check_id, category, message in (
                (
                    "WX-001",
                    "weather_wind",
                    "Aircraft wind limits could not be read, so wind could not "
                    "be assessed against them.",
                ),
                (
                    "WX-002",
                    "weather_precipitation",
                    "Aircraft precipitation tolerance could not be read.",
                ),
                (
                    "WX-003",
                    "weather_temperature",
                    "Aircraft operating temperature range could not be read.",
                ),
                (
                    "BAT-001",
                    "battery_endurance",
                    "Aircraft rated flight time could not be read, so endurance "
                    "could not be assessed.",
                ),
                (
                    "MNT-001",
                    "airworthiness",
                    "The drone could not be resolved, so its service history "
                    "was not read.",
                ),
                (
                    "MNT-002",
                    "aircraft_state",
                    "Aircraft Service was unavailable, so the drone's readiness "
                    "state is unknown.",
                ),
            )
        )

    checks: list[CheckDetail] = []

    if weather is None:
        checks.extend(
            CheckDetail(
                check_id=check_id,
                category=category,
                result=CheckResult.UNAVAILABLE,
                message="Weather source was unavailable.",
            )
            for check_id, category in (
                ("WX-001", "weather_wind"),
                ("WX-002", "weather_precipitation"),
                ("WX-003", "weather_temperature"),
            )
        )
    else:
        checks.extend(check_weather(weather=weather, aircraft=aircraft))

    if battery is None:
        checks.append(
            CheckDetail(
                check_id="BAT-001",
                category="battery_endurance",
                result=CheckResult.UNAVAILABLE,
                message="Battery state was unavailable.",
            )
        )
    else:
        checks.append(
            check_endurance(
                battery=battery,
                aircraft=aircraft,
                mission_duration_min=duration,
                weather=weather,
            )
        )

    checks.extend(check_airworthiness(aircraft=aircraft, maintenance=maintenance))

    return tuple(checks)


def _select_weather_source(
    *,
    request: FlightReadinessRequest,
    now: datetime,
    forecast_source: WeatherSource,
    observation_source: WeatherSource | None,
) -> WeatherSource:
    """Infer the source from time-to-start. No flag is supplied by the model."""
    lead_hours = (request.planned_start_time - now).total_seconds() / 3600
    if lead_hours <= LIVE_OBSERVATION_HORIZON_HOURS and observation_source is not None:
        return observation_source
    return forecast_source


def _mission_duration(request: FlightReadinessRequest) -> tuple[float | None, bool]:
    if request.mission_duration_min is not None:
        return request.mission_duration_min, False
    window = request.planned_end_time - request.planned_start_time
    return window.total_seconds() / 60, True


def _fetch_aircraft(
    client: AircraftClient, drone: str
) -> tuple[AircraftRecord | None, Exception | None]:
    try:
        return client.get_aircraft(drone=drone), None
    except DroneNotFoundError as exc:
        return None, exc
    except AircraftDataUnavailableError as exc:
        return None, exc


def _apply_pilot_battery(
    battery: BatteryRecord | None,
    request: FlightReadinessRequest,
    *,
    now: datetime,
) -> tuple[BatteryRecord | None, tuple[str, ...]]:
    """Fall back to a pilot-reported charge when no system can supply one.

    Verified against the live sandbox: Plex exposes battery state nowhere —
    no endpoint, no field on the drone record, none on the flight record. It
    exists only in live telemetry, which emits only while a drone is flying.
    So for a pre-flight check the pilot reading the controller is often the
    only source there is.

    System data always wins. A pilot figure is used only to fill a gap, and is
    always recorded as an assumption so the number can be told apart from a
    measured one.
    """
    reported = request.battery_charge_percent
    if reported is None:
        return battery, ()

    if battery is not None and battery.state_of_charge is not None:
        return battery, (
            "Battery charge was supplied by the pilot but a system reading was "
            "available, so the system reading was used.",
        )

    fraction = reported / 100.0
    assumption = (
        f"Battery charge of {reported:.0f}% was reported by the pilot, not "
        f"read from Plex or live telemetry."
    )

    if battery is None:
        return (
            BatteryRecord(state_of_charge=fraction, observed_at=now),
            (assumption,),
        )

    return replace(battery, state_of_charge=fraction, observed_at=now), (assumption,)


def _fetch_battery(
    client: AircraftClient, aircraft: AircraftRecord | None
) -> BatteryRecord | None:
    if aircraft is None:
        return None
    try:
        return client.get_battery(drone_id=aircraft.drone_id)
    except AircraftDataUnavailableError:
        return None


def _fetch_maintenance(
    reader: MaintenanceReader, aircraft: AircraftRecord | None
) -> MaintenanceSnapshot | None:
    if aircraft is None:
        return None
    try:
        return reader.get_maintenance_status(drone_id=aircraft.drone_id)
    except MaintenanceDataUnavailableError:
        return None


def _fetch_weather(
    source: WeatherSource, request: FlightReadinessRequest
) -> WeatherRecord | None:
    try:
        return source.get_weather(
            longitude=request.location.longitude,
            latitude=request.location.latitude,
            altitude_m=request.planned_altitude_m,
            valid_from=request.planned_start_time,
            valid_until=request.planned_end_time,
        )
    except (WeatherDataUnavailableError, ForecastHorizonExceededError):
        return None
