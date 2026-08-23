import pytest

from tools.flight_readiness.decision_types import CheckResult
from tools.flight_readiness.predictors.weather_predictor import check_weather
from tools.flight_readiness.tests.fixtures import aircraft_responses as ac
from tools.flight_readiness.tests.fixtures import weather_responses as wx


def wind(weather, aircraft=ac.READY):
    checks = {c.check_id: c for c in check_weather(weather=weather, aircraft=aircraft)}
    return checks["WX-001"]


def precipitation(weather, aircraft=ac.READY):
    checks = {c.check_id: c for c in check_weather(weather=weather, aircraft=aircraft)}
    return checks["WX-002"]


def temperature(weather, aircraft=ac.READY):
    checks = {c.check_id: c for c in check_weather(weather=weather, aircraft=aircraft)}
    return checks["WX-003"]


def test_returns_three_checks() -> None:
    checks = check_weather(weather=wx.CALM, aircraft=ac.READY)
    assert [c.check_id for c in checks] == ["WX-001", "WX-002", "WX-003"]


def test_calm_conditions_all_clear() -> None:
    checks = check_weather(weather=wx.CALM, aircraft=ac.READY)
    assert all(c.result is CheckResult.CLEAR for c in checks)


def test_gust_in_warning_band() -> None:
    assert wind(wx.GUST_IN_WARNING_BAND).result is CheckResult.WARNING


def test_sustained_above_ceiling_fails() -> None:
    assert wind(wx.SUSTAINED_ABOVE_CEILING).result is CheckResult.FAIL


def test_gust_above_ceiling_fails_even_with_sustained_below() -> None:
    # The case a sustained-wind-only check would wrongly clear.
    check = wind(wx.GUST_ABOVE_CEILING_SUSTAINED_BELOW)
    assert check.result is CheckResult.FAIL
    assert check.observed["sustained_ms"] < check.threshold["operational_ceiling_ms"]


def test_operational_ceiling_is_derated() -> None:
    check = wind(wx.CALM)
    assert check.threshold["rated_max_ms"] == 12.0
    assert check.threshold["operational_ceiling_ms"] == pytest.approx(7.8)


def test_missing_gust_caps_at_warning() -> None:
    # Sustained wind is below the band, but gust is the dominant risk and this
    # source publishes none. Clearing on sustained alone would be a false CLEAR.
    check = wind(wx.GUST_MISSING)
    assert check.result is CheckResult.WARNING
    assert any("gust" in a for a in check.assumptions)


def test_unknown_model_has_no_wind_limit() -> None:
    check = wind(wx.CALM, aircraft=ac.UNKNOWN_MODEL_NO_LIMITS)
    assert check.result is CheckResult.UNAVAILABLE


def test_precipitation_above_tolerance_fails() -> None:
    assert precipitation(wx.PRECIPITATION_PRESENT).result is CheckResult.FAIL


def test_no_precipitation_is_clear() -> None:
    assert precipitation(wx.CALM).result is CheckResult.CLEAR


def test_precipitation_unavailable_without_tolerance() -> None:
    check = precipitation(wx.CALM, aircraft=ac.UNKNOWN_MODEL_NO_LIMITS)
    assert check.result is CheckResult.UNAVAILABLE


def test_temperature_too_hot_fails() -> None:
    assert temperature(wx.TEMPERATURE_TOO_HOT).result is CheckResult.FAIL


def test_temperature_too_cold_fails() -> None:
    assert temperature(wx.TEMPERATURE_TOO_COLD).result is CheckResult.FAIL


def test_temperature_in_range_is_clear() -> None:
    assert temperature(wx.CALM).result is CheckResult.CLEAR


def test_checks_carry_observed_and_threshold() -> None:
    # The model explains "why" from these, so every check must populate them.
    for check in check_weather(weather=wx.GUST_IN_WARNING_BAND, aircraft=ac.READY):
        assert check.observed
        assert check.threshold
        assert check.message


def test_predictor_never_raises_on_empty_weather() -> None:
    from tools.flight_readiness.request_response_schemas import WeatherRecord

    empty = WeatherRecord(source="open-meteo", valid_at=wx.VALID_AT)
    checks = check_weather(weather=empty, aircraft=ac.READY)
    assert all(c.result is CheckResult.UNAVAILABLE for c in checks)
