"""Adapter tests: raw Plex payloads to this tool's records.

Payload shapes follow the field names the working MCP server already relies on
(name, serial_number, drone_model_id, status, serviceable, drone_id). The
operating-limit keys are still unverified, so the adapter tries several and
these tests pin the fallback behaviour rather than any one key.
"""

import pytest

from tools.flight_readiness.garuda_aircraft_adapter import (
    MODEL_ID_TO_NAME,
    resolve_model_name,
    to_aircraft_record,
    to_battery_record,
)

PLEX_DRONE = {
    "drone_id": "DRONE-001",
    "name": "Falcon 1",
    "serial_number": "SN-0001",
    "drone_model_id": "MODEL-M4",
    "status": "RTF",
    "serviceable": True,
}


def test_maps_confirmed_fields() -> None:
    record = to_aircraft_record(PLEX_DRONE)
    assert record.drone_id == "DRONE-001"
    assert record.name == "Falcon 1"
    assert record.status == "RTF"
    assert record.serviceable is True


def test_missing_identifier_is_rejected() -> None:
    with pytest.raises(ValueError):
        to_aircraft_record({"name": "Falcon 1", "status": "RTF"})


def test_unmapped_model_id_yields_no_limits() -> None:
    # The id-to-name map is empty until Swagger is checked, so limits are
    # unknown — which must surface as None, never as permissive defaults.
    record = to_aircraft_record(PLEX_DRONE)
    assert record.limits_source is None
    assert record.max_wind_resistance_ms is None
    assert record.max_flight_time_min is None


def test_mapped_model_id_falls_back_to_local_specs(monkeypatch) -> None:
    monkeypatch.setitem(MODEL_ID_TO_NAME, "MODEL-M4", "Matrice 4")
    record = to_aircraft_record(PLEX_DRONE)
    assert record.limits_source == "local_specs"
    assert record.max_wind_resistance_ms == 12.0


def test_plex_limits_win_over_local_specs() -> None:
    payload = {**PLEX_DRONE, "drone_model": "Matrice 4", "max_wind_resistance": 9.5}
    record = to_aircraft_record(payload)
    assert record.limits_source == "plex"
    assert record.max_wind_resistance_ms == 9.5


def test_nested_model_object_is_read() -> None:
    payload = {
        **PLEX_DRONE,
        "drone_model": {"model_name": "Matrice 4", "max_flight_time": 38},
    }
    record = to_aircraft_record(payload)
    assert record.max_flight_time_min == 38.0


def test_explicit_model_name_beats_model_id() -> None:
    assert resolve_model_name({"drone_model": "Matrice 350 RTK"}) == "Matrice 350 RTK"
    assert resolve_model_name({"drone_model_id": "UNKNOWN-ID"}) is None


def test_serviceable_absent_is_none_not_false() -> None:
    record = to_aircraft_record({k: v for k, v in PLEX_DRONE.items() if k != "serviceable"})
    assert record.serviceable is None


def test_flying_state_detected_from_string() -> None:
    assert to_aircraft_record({**PLEX_DRONE, "flight_state": "flying"}).is_flying
    assert not to_aircraft_record({**PLEX_DRONE, "flight_state": "idle"}).is_flying


# --- battery ----------------------------------------------------------------


def test_percentage_charge_is_normalised_to_a_fraction() -> None:
    # A 95 read as 95.0 rather than 0.95 would inflate endurance a hundredfold.
    record = to_battery_record({"state_of_charge": 95, "state_of_health": 98})
    assert record.state_of_charge == pytest.approx(0.95)
    assert record.state_of_health == pytest.approx(0.98)


def test_fractional_charge_is_left_alone() -> None:
    record = to_battery_record({"soc": 0.42})
    assert record.state_of_charge == pytest.approx(0.42)


def test_alternate_key_names_are_accepted() -> None:
    record = to_battery_record({"battery_percentage": 80, "cycles": 120})
    assert record.state_of_charge == pytest.approx(0.80)
    assert record.cycle_count == 120


def test_empty_battery_payload_yields_empty_record() -> None:
    record = to_battery_record(None)
    assert record.state_of_charge is None
    assert record.state_of_health is None


def test_timestamps_are_made_timezone_aware() -> None:
    record = to_aircraft_record({**PLEX_DRONE, "updated_at": "2026-08-25T08:45:00"})
    assert record.observed_at is not None
    assert record.observed_at.tzinfo is not None
