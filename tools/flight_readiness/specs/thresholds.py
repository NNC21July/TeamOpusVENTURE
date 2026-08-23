"""Policy constants for the readiness predictors.

None of these are per-model limits — those live in model_limits.py. These are
operating policy: how far below a rated limit we choose to stop, how much
battery reserve we insist on, how stale data may be before confidence drops.

Every value here is an ASSUMPTION pending client confirmation. Each has a
matching entry in ASSUMPTION_TEXT so a predictor that relies on one can record
why the number was used, in the tool's `assumptions` output.

If Garuda already has a manual go/no-go checklist, that checklist is the
specification and these values should be replaced by it wholesale.
"""

# --- Wind -------------------------------------------------------------------

# Operational ceiling = rated max wind resistance x this factor.
# Industry practice is to operate at 60-70% of rated wind resistance.
WIND_DERATING_FACTOR = 0.65

# A wind or gust reading at or above this fraction of the operational ceiling
# is WARNING rather than CLEAR.
WIND_WARNING_BAND_FRACTION = 0.85


# --- Endurance --------------------------------------------------------------

# Minutes of flight that must remain unused at the end of the mission.
BATTERY_RESERVE_MINUTES = 5.0

# If available endurance exceeds the requirement by less than this, WARNING.
ENDURANCE_WARNING_MARGIN_MINUTES = 3.0

# Used when the battery reports no state of health. Optimistic by definition,
# so a predictor applying it must downgrade confidence and record the assumption.
DEFAULT_STATE_OF_HEALTH = 1.0

# Below this charge fraction the aircraft should not launch at all.
MINIMUM_LAUNCH_CHARGE_FRACTION = 0.30

# Endurance falls in wind as the aircraft works to hold position. Keyed by
# sustained wind as a fraction of the operational ceiling, mapping to the
# fraction of rated flight time still achievable. Interpolate between points.
WIND_ENDURANCE_PENALTY: tuple[tuple[float, float], ...] = (
    (0.00, 1.00),
    (0.25, 0.95),
    (0.50, 0.88),
    (0.75, 0.78),
    (1.00, 0.70),
)


# --- Forecast horizons ------------------------------------------------------

# Under this, prefer live observations over forecast.
LIVE_OBSERVATION_HORIZON_HOURS = 2

# Beyond these, the respective source cannot answer at all.
NEA_FORECAST_HORIZON_DAYS = 4
OPEN_METEO_FORECAST_HORIZON_DAYS = 16


# --- Staleness --------------------------------------------------------------

NEA_OBSERVATION_MAX_AGE_MINUTES = 15
OPEN_METEO_FORECAST_MAX_AGE_HOURS = 6
BATTERY_STATE_MAX_AGE_HOURS = 24
MAINTENANCE_RECORD_MAX_AGE_DAYS = 7


# --- Assumption text --------------------------------------------------------

# Keyed so a predictor can do: assumptions.append(ASSUMPTION_TEXT["wind_derating"])
ASSUMPTION_TEXT: dict[str, str] = {
    "wind_derating": (
        f"Operational ceiling derived by derating rated max wind by "
        f"{WIND_DERATING_FACTOR:.2f}; factor not yet confirmed with client."
    ),
    "wind_warning_band": (
        f"Warning band set at {WIND_WARNING_BAND_FRACTION:.0%} of the operational "
        f"ceiling; not yet confirmed with client."
    ),
    "battery_reserve": (
        f"Battery reserve of {BATTERY_RESERVE_MINUTES:.0f} minutes applied; "
        f"not yet confirmed with client."
    ),
    "default_state_of_health": (
        "Battery state of health unavailable; assumed nominal."
    ),
    "wind_endurance_penalty": (
        "Endurance reduced for wind using an unvalidated penalty curve."
    ),
    "local_model_limits": (
        "Operating limits taken from the local specification table rather than "
        "Plex; values are locally sourced from manufacturer datasheets."
    ),
}
