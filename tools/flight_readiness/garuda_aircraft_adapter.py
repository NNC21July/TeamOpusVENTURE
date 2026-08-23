"""Normalise raw Plex drone payloads into this tool's records.

Kept separate from the client, mirroring the route compliance tool's split
between garuda_airspace_client and garuda_airspace_adapter, so the field
mapping can be tested without any HTTP.

Field names confirmed from the working MCP server shaping code:

    name, serial_number, drone_model_id, status, serviceable, drone_id

Two consequences worth knowing:

  * Plex identifies a model by `drone_model_id`, not by a model name string.
    The local specs table is keyed by name, so a lookup needs the id-to-name
    mapping in MODEL_ID_TO_NAME below. That mapping is UNCONFIRMED and is the
    first thing to check once sandbox credentials are available.
  * `serviceable` is a Plex-native airworthiness flag. It is carried through
    onto the record so the airworthiness predictor can use it directly rather
    than inferring the same thing from maintenance history.

Every operating-limit field is still unverified against Swagger, so the
adapter tries a list of candidate keys and falls back to the local specs
table, recording which source won in `limits_source`.
"""

from datetime import datetime, timezone
from typing import Any

from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    BatteryRecord,
)
from tools.flight_readiness.specs.model_limits import ModelLimits, get_model_limits

# UNCONFIRMED. Populate from GET /aircraft/drone-models once credentials exist.
MODEL_ID_TO_NAME: dict[str, str] = {}

# Candidate key names for each limit, tried in order. Plex may nest these
# under the drone, under a model sub-object, or not expose them at all.
_LIMIT_KEYS: dict[str, tuple[str, ...]] = {
    "max_wind_resistance_ms": ("max_wind_resistance", "max_wind_speed", "wind_limit"),
    "max_flight_time_min": ("max_flight_time", "max_flight_duration", "endurance_min"),
    "operating_temp_min_c": ("operating_temp_min", "min_operating_temperature"),
    "operating_temp_max_c": ("operating_temp_max", "max_operating_temperature"),
    "precipitation_tolerance_mm_h": (
        "precipitation_tolerance",
        "rain_tolerance",
        "ip_rating_mm_h",
    ),
}

_BATTERY_KEYS: dict[str, tuple[str, ...]] = {
    "state_of_charge": ("state_of_charge", "soc", "battery_percentage", "capacity"),
    "state_of_health": ("state_of_health", "soh", "health"),
    "cycle_count": ("cycle_count", "cycles", "charge_cycles"),
    "battery_id": ("battery_id", "id", "serial_number"),
}


def resolve_model_name(raw: dict[str, Any]) -> str | None:
    """Best available model name for a drone record.

    Prefers an explicit name if Plex supplies one, otherwise maps the model id
    through MODEL_ID_TO_NAME. Returns None when neither is possible, which the
    predictors must treat as "limits unknown" rather than "no limits".
    """
    for key in ("drone_model", "model", "model_name"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    model_id = raw.get("drone_model_id")
    if isinstance(model_id, str):
        return MODEL_ID_TO_NAME.get(model_id)
    return None


def to_aircraft_record(raw: dict[str, Any]) -> AircraftRecord:
    """Build an AircraftRecord from one Plex drone payload."""
    drone_id = _first(raw, ("drone_id", "id", "_id"))
    if not drone_id:
        raise ValueError("drone payload has no identifier")

    model_name = resolve_model_name(raw)
    limits, limits_source = _resolve_limits(raw, model_name)

    status = raw.get("status")
    serviceable = raw.get("serviceable")

    return AircraftRecord(
        drone_id=str(drone_id),
        model=model_name or str(raw.get("drone_model_id") or "unknown"),
        status=str(status) if status is not None else "",
        name=raw.get("name") or raw.get("serial_number"),
        max_wind_resistance_ms=limits.max_wind_resistance_ms,
        max_flight_time_min=limits.max_flight_time_min,
        operating_temp_min_c=limits.operating_temp_min_c,
        operating_temp_max_c=limits.operating_temp_max_c,
        precipitation_tolerance_mm_h=limits.precipitation_tolerance_mm_h,
        is_flying=_is_flying(raw),
        serviceable=bool(serviceable) if serviceable is not None else None,
        limits_source=limits_source,
        observed_at=_timestamp(raw) or datetime.now(timezone.utc),
    )


def to_battery_record(raw: dict[str, Any] | None) -> BatteryRecord:
    """Build a BatteryRecord from a battery payload or live telemetry frame.

    Charge is normalised to a 0-1 fraction: Plex may report a percentage, and
    a 95 read as 0.95 versus 95.0 is the difference between a sane endurance
    figure and a wildly optimistic one.
    """
    if not raw:
        return BatteryRecord()

    charge = _first(raw, _BATTERY_KEYS["state_of_charge"])
    health = _first(raw, _BATTERY_KEYS["state_of_health"])

    return BatteryRecord(
        battery_id=_stringify(_first(raw, _BATTERY_KEYS["battery_id"])),
        state_of_charge=_as_fraction(charge),
        state_of_health=_as_fraction(health),
        cycle_count=_as_int(_first(raw, _BATTERY_KEYS["cycle_count"])),
        observed_at=_timestamp(raw) or datetime.now(timezone.utc),
    )


def _resolve_limits(
    raw: dict[str, Any], model_name: str | None
) -> tuple[ModelLimits, str | None]:
    nested = raw.get("drone_model") if isinstance(raw.get("drone_model"), dict) else {}
    merged = {**raw, **nested}

    found = {
        field: _as_float(_first(merged, keys)) for field, keys in _LIMIT_KEYS.items()
    }

    if any(value is not None for value in found.values()):
        return ModelLimits(model=model_name or "unknown", **found), "plex"

    local = get_model_limits(model_name)
    if local is not None:
        return local, "local_specs"

    # Neither source knows this airframe. Returning empty limits is correct:
    # the predictors turn missing limits into UNAVAILABLE, never into "fine".
    return ModelLimits(model=model_name or "unknown"), None


def _is_flying(raw: dict[str, Any]) -> bool:
    for key in ("is_flying", "flying", "in_flight"):
        if isinstance(raw.get(key), bool):
            return raw[key]
    flight_state = raw.get("flight_state") or raw.get("state")
    return isinstance(flight_state, str) and flight_state.lower() == "flying"


def _timestamp(raw: dict[str, Any]) -> datetime | None:
    for key in ("last_modified_at", "updated_at", "timestamp", "observed_at"):
        value = raw.get(key)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    return None


def _first(raw: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if raw.get(key) is not None:
            return raw[key]
    return None


def _as_fraction(value: Any) -> float | None:
    """Normalise a charge or health figure to 0-1, accepting 0-100 percentages."""
    number = _as_float(value)
    if number is None:
        return None
    if number > 1.0:
        return number / 100.0
    return number


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return int(number) if number is not None else None


def _stringify(value: Any) -> str | None:
    return str(value) if value is not None else None
