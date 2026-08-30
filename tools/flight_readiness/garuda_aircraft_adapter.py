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

# Model ids seen in the NTU sandbox fleet, confirmed against
# GET /aircraft/drone-models. This is a cache, not the source of truth: any id
# not listed is resolved live through the catalogue and added here.
MODEL_ID_TO_NAME: dict[str, str] = {
    "3f9d721a48c2b08c1fd03bc67b03d88f": "Cerana ONE Pro",
    "520a86d7e4137e76bcf4a9f2134cf2dd": "Garuda Robotics V220",
}

# Flight time in minutes, as published by Plex on the model record. Populated
# alongside the name whenever a model is resolved.
MODEL_ID_TO_FLIGHT_TIME: dict[str, float] = {
    "3f9d721a48c2b08c1fd03bc67b03d88f": 42.0,
}


def resolve_model_from_catalogue(drone_model_id: str) -> tuple[str | None, float | None]:
    """Look a model id up in Plex, caching the result.

    Called only on a cache miss, so a fleet of known models costs no extra
    requests. Failure is not an error: an unresolvable model means the
    predictors report UNAVAILABLE, which is the correct conservative outcome.
    """
    if not drone_model_id:
        return None, None
    if drone_model_id in MODEL_ID_TO_NAME:
        return (
            MODEL_ID_TO_NAME[drone_model_id],
            MODEL_ID_TO_FLIGHT_TIME.get(drone_model_id),
        )

    try:
        from api_client import rest_client

        model = rest_client.get_drone_model(drone_model_id)
    except Exception:
        return None, None

    name = model.get("name") if isinstance(model, dict) else None
    flight_time = _as_float(model.get("max_flight_time")) if isinstance(model, dict) else None

    if isinstance(name, str) and name.strip():
        MODEL_ID_TO_NAME[drone_model_id] = name.strip()
        if flight_time is not None:
            MODEL_ID_TO_FLIGHT_TIME[drone_model_id] = flight_time
        return name.strip(), flight_time
    return None, flight_time

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
        name, _ = resolve_model_from_catalogue(model_id)
        return name
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
    """Merge what Plex publishes with what only the local table knows.

    Verified against the live sandbox: a Plex drone model carries
    `max_flight_time` and nothing else. Wind resistance, temperature range and
    precipitation tolerance exist in no Plex field, so they can only come from
    the local table. Neither source is complete on its own, so they are merged
    and `limits_source` records which contributed.
    """
    nested = raw.get("drone_model") if isinstance(raw.get("drone_model"), dict) else {}
    merged = {**raw, **nested}

    found = {
        field: _as_float(_first(merged, keys)) for field, keys in _LIMIT_KEYS.items()
    }

    # A drone record references its model by id, so the authoritative flight
    # time lives on the model record rather than the drone.
    model_id = raw.get("drone_model_id")
    if found["max_flight_time_min"] is None and isinstance(model_id, str):
        _, catalogue_flight_time = resolve_model_from_catalogue(model_id)
        if catalogue_flight_time is not None:
            found["max_flight_time_min"] = catalogue_flight_time

    from_plex = any(value is not None for value in found.values())
    local = get_model_limits(model_name)

    if local is not None:
        merged_limits = ModelLimits(
            model=local.model,
            # Plex wins where it publishes a value; the local table fills the
            # three limits Plex does not expose at all.
            max_wind_resistance_ms=found["max_wind_resistance_ms"]
            or local.max_wind_resistance_ms,
            max_flight_time_min=found["max_flight_time_min"]
            or local.max_flight_time_min,
            operating_temp_min_c=found["operating_temp_min_c"]
            if found["operating_temp_min_c"] is not None
            else local.operating_temp_min_c,
            operating_temp_max_c=found["operating_temp_max_c"]
            if found["operating_temp_max_c"] is not None
            else local.operating_temp_max_c,
            precipitation_tolerance_mm_h=found["precipitation_tolerance_mm_h"]
            if found["precipitation_tolerance_mm_h"] is not None
            else local.precipitation_tolerance_mm_h,
        )
        return merged_limits, "plex+local_specs" if from_plex else "local_specs"

    if from_plex:
        return ModelLimits(model=model_name or "unknown", **found), "plex"

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
