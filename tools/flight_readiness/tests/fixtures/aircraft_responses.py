"""Aircraft records for predictor tests.

READY is the baseline every other fixture varies from: a Matrice 4, ready to
fly, with limits supplied by Plex.
"""

from datetime import datetime, timedelta, timezone

from tools.flight_readiness.request_response_schemas import AircraftRecord

SG_TIMEZONE = timezone(timedelta(hours=8))

OBSERVED_AT = datetime(2026, 8, 25, 8, 45, tzinfo=SG_TIMEZONE)


READY = AircraftRecord(
    drone_id="DRONE-001",
    model="Matrice 4",
    status="RTF",
    name="Falcon 1",
    max_wind_resistance_ms=12.0,
    max_flight_time_min=45.0,
    operating_temp_min_c=-10.0,
    operating_temp_max_c=40.0,
    precipitation_tolerance_mm_h=0.0,
    is_flying=False,
    limits_source="plex",
    observed_at=OBSERVED_AT,
)

NOT_READY_TO_FLY = AircraftRecord(
    drone_id="DRONE-002",
    model="Matrice 4",
    status="INIT",
    name="Falcon 2",
    max_wind_resistance_ms=12.0,
    max_flight_time_min=45.0,
    operating_temp_min_c=-10.0,
    operating_temp_max_c=40.0,
    precipitation_tolerance_mm_h=0.0,
    is_flying=False,
    limits_source="plex",
    observed_at=OBSERVED_AT,
)

ALREADY_FLYING = AircraftRecord(
    drone_id="DRONE-003",
    model="Matrice 4",
    status="RTF",
    name="Falcon 3",
    max_wind_resistance_ms=12.0,
    max_flight_time_min=45.0,
    operating_temp_min_c=-10.0,
    operating_temp_max_c=40.0,
    precipitation_tolerance_mm_h=0.0,
    is_flying=True,
    limits_source="plex",
    observed_at=OBSERVED_AT,
)

# Plex had no limits; the local specs table supplied them instead.
LIMITS_FROM_LOCAL_SPECS = AircraftRecord(
    drone_id="DRONE-004",
    model="Matrice 4",
    status="RTF",
    name="Falcon 4",
    max_wind_resistance_ms=12.0,
    max_flight_time_min=45.0,
    operating_temp_min_c=-10.0,
    operating_temp_max_c=40.0,
    precipitation_tolerance_mm_h=0.0,
    is_flying=False,
    limits_source="local_specs",
    observed_at=OBSERVED_AT,
)

# Neither Plex nor the local table knows this model. Must be UNAVAILABLE,
# never treated as unlimited.
UNKNOWN_MODEL_NO_LIMITS = AircraftRecord(
    drone_id="DRONE-005",
    model="Prototype X",
    status="RTF",
    name="Falcon 5",
    is_flying=False,
    limits_source=None,
    observed_at=OBSERVED_AT,
)

# Aircraft state older than the staleness policy allows.
STALE_STATE = AircraftRecord(
    drone_id="DRONE-006",
    model="Matrice 4",
    status="RTF",
    name="Falcon 6",
    max_wind_resistance_ms=12.0,
    max_flight_time_min=45.0,
    operating_temp_min_c=-10.0,
    operating_temp_max_c=40.0,
    precipitation_tolerance_mm_h=0.0,
    is_flying=False,
    limits_source="plex",
    observed_at=OBSERVED_AT - timedelta(days=4),
)
