"""End-to-end tests for check_flight_readiness.

The predictor tests cover each factor in isolation. These cover the assembled
service: decision aggregation, the confidence downgrade, and the precedence
rules between them. Driven entirely by fakes — no network, no clock.

Each test maps to a row of the Research 2 test table.
"""

from datetime import datetime, timedelta, timezone

from tools.flight_readiness.decision_types import (
    CheckResult,
    ConfidenceLevel,
    OverallDecision,
)
from tools.flight_readiness.output_shaper import shape_flight_readiness_response
from tools.flight_readiness.request_response_schemas import (
    FlightReadinessRequest,
    Location,
)
from tools.flight_readiness.service import check_flight_readiness
from tools.flight_readiness.tests.fakes import (
    FakeAircraftClient,
    FakeMaintenanceReader,
    FakeWeatherSource,
)
from tools.flight_readiness.tests.fixtures import aircraft_responses as ac
from tools.flight_readiness.tests.fixtures import battery_states as bat
from tools.flight_readiness.tests.fixtures import maintenance_records as mnt
from tools.flight_readiness.tests.fixtures import weather_responses as wx

SG = timezone(timedelta(hours=8))
NOW = datetime(2026, 8, 25, 8, 0, tzinfo=SG)


def make_request(*, lead=timedelta(hours=1), duration=25.0, **overrides):
    defaults = dict(
        drone="DRONE-001",
        planned_start_time=NOW + lead,
        planned_end_time=NOW + lead + timedelta(hours=1),
        location=Location(longitude=103.8010, latitude=1.3010),
        planned_altitude_m=60.0,
        mission_duration_min=duration,
    )
    defaults.update(overrides)
    return FlightReadinessRequest(**defaults)


def run(
    *,
    request=None,
    aircraft=ac.READY,
    battery=bat.HEALTHY,
    maintenance=mnt.FRESHLY_SERVICED,
    weather=wx.CALM,
    aircraft_client=None,
    weather_source=None,
):
    return check_flight_readiness(
        request=request or make_request(),
        aircraft_client=aircraft_client or FakeAircraftClient(aircraft, battery),
        maintenance_reader=FakeMaintenanceReader(maintenance),
        forecast_source=weather_source or FakeWeatherSource(weather),
        now=NOW,
    )


def result_for(response, check_id):
    return next(c.result for c in response.checks if c.check_id == check_id)


# --- the happy path ---------------------------------------------------------


def test_clear_weather_healthy_battery_serviced_airframe_is_go() -> None:
    response = run()
    assert response.decision is OverallDecision.GO
    assert all(c.result is CheckResult.CLEAR for c in response.checks)
    assert response.confidence.level is ConfidenceLevel.HIGH
    assert not response.blocking_factors


# --- weather ----------------------------------------------------------------


def test_gust_in_warning_band_is_go_with_warnings() -> None:
    response = run(weather=wx.GUST_IN_WARNING_BAND)
    assert response.decision is OverallDecision.GO_WITH_WARNINGS
    assert result_for(response, "WX-001") is CheckResult.WARNING


def test_sustained_wind_above_ceiling_is_no_go() -> None:
    response = run(weather=wx.SUSTAINED_ABOVE_CEILING)
    assert response.decision is OverallDecision.NO_GO
    assert result_for(response, "WX-001") is CheckResult.FAIL


def test_gust_above_ceiling_with_sustained_below_is_no_go() -> None:
    response = run(weather=wx.GUST_ABOVE_CEILING_SUSTAINED_BELOW)
    assert response.decision is OverallDecision.NO_GO


def test_precipitation_against_zero_tolerance_is_no_go() -> None:
    response = run(weather=wx.PRECIPITATION_PRESENT)
    assert response.decision is OverallDecision.NO_GO
    assert result_for(response, "WX-002") is CheckResult.FAIL


# --- endurance --------------------------------------------------------------


def test_mission_exceeding_endurance_is_no_go() -> None:
    response = run(battery=bat.PARTIALLY_CHARGED)
    assert response.decision is OverallDecision.NO_GO
    assert result_for(response, "BAT-001") is CheckResult.FAIL


def test_thin_endurance_margin_is_go_with_warnings() -> None:
    response = run(request=make_request(duration=32.0))
    assert response.decision is OverallDecision.GO_WITH_WARNINGS
    assert result_for(response, "BAT-001") is CheckResult.WARNING


def test_missing_state_of_health_records_an_assumption() -> None:
    response = run(battery=bat.STATE_OF_HEALTH_MISSING)
    assert any("state of health" in a for a in response.assumptions)


# --- airworthiness ----------------------------------------------------------


def test_overdue_maintenance_is_no_go() -> None:
    response = run(maintenance=mnt.OVERDUE_ON_HOURS)
    assert response.decision is OverallDecision.NO_GO
    assert result_for(response, "MNT-001") is CheckResult.FAIL


def test_due_soon_maintenance_is_go_with_warnings() -> None:
    response = run(maintenance=mnt.NEAR_SERVICE_INTERVAL)
    assert response.decision is OverallDecision.GO_WITH_WARNINGS
    assert result_for(response, "MNT-001") is CheckResult.WARNING


def test_drone_not_ready_to_fly_is_no_go() -> None:
    response = run(aircraft=ac.NOT_READY_TO_FLY)
    assert response.decision is OverallDecision.NO_GO
    assert result_for(response, "MNT-002") is CheckResult.FAIL


# --- unavailable data -------------------------------------------------------


def test_weather_source_error_is_unknown() -> None:
    response = run(weather_source=FakeWeatherSource(unavailable=True))
    assert response.decision is OverallDecision.UNKNOWN
    assert result_for(response, "WX-001") is CheckResult.UNAVAILABLE
    # The other predictors still ran: a pilot sees every factor at once.
    assert result_for(response, "BAT-001") is CheckResult.CLEAR
    assert result_for(response, "MNT-001") is CheckResult.CLEAR


def test_no_go_outranks_unknown() -> None:
    # Wind definitively over the ceiling, battery data unavailable. Enough is
    # known to refuse. Absence of a verdict is never read as approval.
    client = FakeAircraftClient(ac.READY, battery=None)
    response = run(weather=wx.SUSTAINED_ABOVE_CEILING, aircraft_client=client)
    assert result_for(response, "BAT-001") is CheckResult.UNAVAILABLE
    assert response.decision is OverallDecision.NO_GO


def test_aircraft_service_unavailable_is_unknown() -> None:
    response = run(aircraft_client=FakeAircraftClient(unavailable=True))
    assert response.decision is OverallDecision.UNKNOWN


def test_fleet_management_unavailable_is_unknown() -> None:
    response = check_flight_readiness(
        request=make_request(),
        aircraft_client=FakeAircraftClient(ac.READY, bat.HEALTHY),
        maintenance_reader=FakeMaintenanceReader(unavailable=True),
        forecast_source=FakeWeatherSource(wx.CALM),
        now=NOW,
    )
    assert response.decision is OverallDecision.UNKNOWN
    assert result_for(response, "MNT-001") is CheckResult.UNAVAILABLE


# --- horizon and confidence -------------------------------------------------


def test_six_days_ahead_all_clear_downgrades_to_go_with_warnings() -> None:
    # Resolves the Research 2 contradiction: the rule wins over the test table.
    # A week-out forecast never reads as a clean GO.
    response = run(request=make_request(lead=timedelta(days=6)))
    assert response.confidence.level is ConfidenceLevel.LOW
    assert response.decision is OverallDecision.GO_WITH_WARNINGS
    assert response.confidence.recommended_recheck is not None


def test_twenty_days_ahead_is_unknown() -> None:
    response = run(request=make_request(lead=timedelta(days=20)))
    assert response.decision is OverallDecision.UNKNOWN


def test_low_confidence_never_softens_no_go() -> None:
    response = run(
        request=make_request(lead=timedelta(days=6)),
        weather=wx.SUSTAINED_ABOVE_CEILING,
    )
    assert response.confidence.level is ConfidenceLevel.LOW
    assert response.decision is OverallDecision.NO_GO


# --- invalid input ----------------------------------------------------------


def test_end_before_start_is_needs_info() -> None:
    response = run(
        request=make_request(planned_end_time=NOW - timedelta(hours=1))
    )
    assert response.decision is OverallDecision.NEEDS_INFO
    assert response.missing_inputs


def test_no_drone_identifier_is_needs_info() -> None:
    response = run(request=make_request(drone="  "))
    assert response.decision is OverallDecision.NEEDS_INFO


def test_unresolvable_drone_is_needs_info_not_unknown() -> None:
    # Bad input, not a broken service.
    response = run(aircraft_client=FakeAircraftClient(not_found=True))
    assert response.decision is OverallDecision.NEEDS_INFO


def test_no_external_call_when_input_is_invalid() -> None:
    source = FakeWeatherSource(wx.CALM)
    client = FakeAircraftClient(ac.READY, bat.HEALTHY)
    run(request=make_request(drone=""), aircraft_client=client, weather_source=source)
    assert source.queries == []
    assert client.aircraft_queries == []


# --- source selection -------------------------------------------------------


def test_imminent_flight_prefers_live_observations() -> None:
    observations = FakeWeatherSource(wx.CALM)
    forecast = FakeWeatherSource(wx.CALM)
    check_flight_readiness(
        request=make_request(lead=timedelta(minutes=30)),
        aircraft_client=FakeAircraftClient(ac.READY, bat.HEALTHY),
        maintenance_reader=FakeMaintenanceReader(mnt.FRESHLY_SERVICED),
        forecast_source=forecast,
        observation_source=observations,
        now=NOW,
    )
    assert observations.queries and not forecast.queries


def test_distant_flight_uses_forecast() -> None:
    observations = FakeWeatherSource(wx.CALM)
    forecast = FakeWeatherSource(wx.CALM)
    check_flight_readiness(
        request=make_request(lead=timedelta(days=3)),
        aircraft_client=FakeAircraftClient(ac.READY, bat.HEALTHY),
        maintenance_reader=FakeMaintenanceReader(mnt.FRESHLY_SERVICED),
        forecast_source=forecast,
        observation_source=observations,
        now=NOW,
    )
    assert forecast.queries and not observations.queries


# --- output shaping ---------------------------------------------------------


def test_shaped_output_is_json_safe() -> None:
    import json

    shaped = shape_flight_readiness_response(run(weather=wx.GUST_IN_WARNING_BAND))
    json.dumps(shaped)  # raises if anything is not serialisable

    assert shaped["decision"] == "GO_WITH_WARNINGS"
    assert shaped["confidence"]["level"] in {"HIGH", "MEDIUM", "LOW"}
    wind = next(c for c in shaped["checks"] if c["check_id"] == "WX-001")
    assert wind["result"] == "WARNING"
    assert "operational_ceiling_ms" in wind["threshold"]


def test_shaped_output_omits_empty_collections() -> None:
    shaped = shape_flight_readiness_response(run())
    assert "blocking_factors" not in shaped
    assert "missing_inputs" not in shaped
