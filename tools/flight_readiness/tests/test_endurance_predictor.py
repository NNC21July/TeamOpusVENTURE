import pytest

from tools.flight_readiness.decision_types import CheckResult
from tools.flight_readiness.predictors.endurance_predictor import check_endurance
from tools.flight_readiness.tests.fixtures import aircraft_responses as ac
from tools.flight_readiness.tests.fixtures import battery_states as bat
from tools.flight_readiness.tests.fixtures import weather_responses as wx


def endurance(battery, *, aircraft=ac.READY, duration=25.0, weather=wx.CALM):
    return check_endurance(
        battery=battery,
        aircraft=aircraft,
        mission_duration_min=duration,
        weather=weather,
    )


def test_healthy_battery_covers_mission() -> None:
    check = endurance(bat.HEALTHY)
    assert check.result is CheckResult.CLEAR
    assert check.observed["available_min"] > check.observed["required_min"]


def test_required_includes_reserve() -> None:
    # required = mission duration + reserve, not the bare mission duration.
    check = endurance(bat.HEALTHY, duration=25.0)
    assert check.observed["required_min"] == pytest.approx(30.0)
    assert check.threshold["reserve_min"] == pytest.approx(5.0)


def test_insufficient_charge_for_mission_fails() -> None:
    check = endurance(bat.PARTIALLY_CHARGED)
    assert check.result is CheckResult.FAIL
    assert check.observed["available_min"] < check.observed["required_min"]


def test_below_minimum_launch_charge_fails() -> None:
    check = endurance(bat.NEARLY_FLAT, duration=5.0)
    # Fails even for a trivially short mission: it is a floor, not a margin.
    assert check.result is CheckResult.FAIL
    assert "minimum launch charge" in check.message


def test_degraded_health_reduces_available_endurance() -> None:
    healthy = endurance(bat.HEALTHY)
    degraded = endurance(bat.DEGRADED)
    assert degraded.observed["available_min"] < healthy.observed["available_min"]


def test_thin_margin_is_a_warning() -> None:
    # Available ~38.2 min; a 32 min mission needs 37 min, leaving 1.2 min.
    check = endurance(bat.HEALTHY, duration=32.0)
    assert check.result is CheckResult.WARNING


def test_missing_state_of_health_assumes_nominal_and_records_it() -> None:
    check = endurance(bat.STATE_OF_HEALTH_MISSING)
    assert check.result is CheckResult.CLEAR
    assert check.observed["state_of_health"] == pytest.approx(1.0)
    assert any("state of health" in a for a in check.assumptions)


def test_missing_charge_is_unavailable() -> None:
    check = endurance(bat.CHARGE_MISSING)
    assert check.result is CheckResult.UNAVAILABLE


def test_unknown_model_has_no_rated_flight_time() -> None:
    check = endurance(bat.HEALTHY, aircraft=ac.UNKNOWN_MODEL_NO_LIMITS)
    assert check.result is CheckResult.UNAVAILABLE


def test_missing_mission_duration_is_unavailable() -> None:
    check = endurance(bat.HEALTHY, duration=None)
    assert check.result is CheckResult.UNAVAILABLE


def test_wind_reduces_available_endurance() -> None:
    # The coupling to the weather predictor: holding position in wind costs
    # flight time, so the same battery yields less endurance.
    calm = endurance(bat.HEALTHY, weather=wx.CALM)
    windy = endurance(bat.HEALTHY, weather=wx.GUST_IN_WARNING_BAND)
    assert windy.observed["available_min"] < calm.observed["available_min"]
    assert windy.observed["wind_penalty"] < calm.observed["wind_penalty"]


def test_no_weather_means_no_wind_penalty() -> None:
    check = endurance(bat.HEALTHY, weather=None)
    assert check.observed["wind_penalty"] == pytest.approx(1.0)


def test_never_raises_on_empty_battery() -> None:
    from tools.flight_readiness.request_response_schemas import BatteryRecord

    check = endurance(BatteryRecord())
    assert check.result is CheckResult.UNAVAILABLE
