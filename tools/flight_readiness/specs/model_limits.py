"""Local fallback table of per-model operating limits.

Used only when Plex does not expose limits for a model. A record sourced from
here must be marked `limits_source="local_specs"` on the AircraftRecord so the
output can say the numbers were locally sourced.

PLACEHOLDER VALUES. Two things are still unverified: which models are actually
in the Garuda fleet, and whether Plex exposes limits at all. Every number below
must be replaced from the manufacturer datasheet before this is trusted.

Deliberately conservative where a datasheet figure is ambiguous: a value that is
too strict produces a false NO_GO, which is recoverable. Too permissive produces
a false GO, which is not.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelLimits:
    # Operating limits for one airframe model. None means the datasheet does
    # not state it — never substitute a permissive default.
    model: str
    max_wind_resistance_ms: float | None = None
    max_flight_time_min: float | None = None
    operating_temp_min_c: float | None = None
    operating_temp_max_c: float | None = None
    precipitation_tolerance_mm_h: float | None = None


# Keyed by the model string as Plex reports it. Lookup is case-insensitive and
# whitespace-tolerant; see get_model_limits below.
MODEL_LIMITS: dict[str, ModelLimits] = {
    "matrice 4": ModelLimits(
        model="Matrice 4",
        max_wind_resistance_ms=12.0,
        max_flight_time_min=45.0,
        operating_temp_min_c=-10.0,
        operating_temp_max_c=40.0,
        precipitation_tolerance_mm_h=0.0,
    ),
    "matrice 350 rtk": ModelLimits(
        model="Matrice 350 RTK",
        max_wind_resistance_ms=12.0,
        max_flight_time_min=55.0,
        operating_temp_min_c=-20.0,
        operating_temp_max_c=50.0,
        precipitation_tolerance_mm_h=0.0,
    ),
    "mavic 3 enterprise": ModelLimits(
        model="Mavic 3 Enterprise",
        max_wind_resistance_ms=12.0,
        max_flight_time_min=45.0,
        operating_temp_min_c=-10.0,
        operating_temp_max_c=40.0,
        precipitation_tolerance_mm_h=0.0,
    ),
}


def get_model_limits(model: str | None) -> ModelLimits | None:
    """Look up limits for a model string, or None if the model is unknown.

    Returning None is meaningful: the caller must treat an unknown model as
    UNAVAILABLE, not as unlimited.
    """
    if not model or not model.strip():
        return None
    return MODEL_LIMITS.get(model.strip().casefold())
