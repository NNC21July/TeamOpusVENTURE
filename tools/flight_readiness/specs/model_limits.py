"""Local table of per-model operating limits.

RESOLVED against the live sandbox: Plex exposes `max_flight_time` on a drone
model and nothing else. There is no wind resistance, no operating temperature
range and no precipitation tolerance anywhere in the model record. So this
table is not a fallback for all four limits — it is the ONLY source for three
of them, and Plex wins on the fourth.

The adapter reads `max_flight_time` from Plex when present and takes the rest
from here, marking the record `limits_source="plex+local_specs"` so the output
says which numbers came from where.

Wind, temperature and precipitation figures below are still PLACEHOLDERS from
general small-UAS practice and must be replaced from manufacturer datasheets.

Deliberately conservative where a figure is ambiguous: too strict produces a
false NO_GO, which is recoverable. Too permissive produces a false GO, which
is not.
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
    # --- models actually present in the NTU sandbox fleet --------------------
    # max_flight_time comes from Plex (42 min for the Cerana ONE Pro) and is
    # repeated here only so the table stands alone if Plex omits it.
    "cerana one pro": ModelLimits(
        model="Cerana ONE Pro",
        max_wind_resistance_ms=12.0,
        max_flight_time_min=42.0,
        operating_temp_min_c=-10.0,
        operating_temp_max_c=45.0,
        precipitation_tolerance_mm_h=0.0,
    ),
    "garuda robotics v220": ModelLimits(
        model="Garuda Robotics V220",
        # A 15 kg fixed-wing tolerates more wind than a quadcopter. Plex does
        # not publish a flight time for this model, so it stays None and the
        # endurance check reports UNAVAILABLE rather than guessing.
        max_wind_resistance_ms=15.0,
        max_flight_time_min=None,
        operating_temp_min_c=-10.0,
        operating_temp_max_c=45.0,
        precipitation_tolerance_mm_h=0.0,
    ),
    # --- speculative entries, kept for models not in this sandbox -----------
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
