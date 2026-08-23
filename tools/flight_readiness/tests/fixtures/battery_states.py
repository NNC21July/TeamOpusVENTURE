"""Battery records for endurance predictor tests.

Paired with a Matrice 4 rated at 45 minutes flight time. Worked example for
HEALTHY, ignoring any wind penalty:

    45.0 rated x 0.98 health x 0.95 charge = 41.9 minutes available
"""

from datetime import datetime, timedelta, timezone

from tools.flight_readiness.request_response_schemas import BatteryRecord

SG_TIMEZONE = timezone(timedelta(hours=8))

OBSERVED_AT = datetime(2026, 8, 25, 8, 45, tzinfo=SG_TIMEZONE)


HEALTHY = BatteryRecord(
    battery_id="BAT-001",
    state_of_charge=0.95,
    state_of_health=0.98,
    cycle_count=42,
    observed_at=OBSERVED_AT,
)

# 45.0 x 0.95 x 0.45 = 19.2 minutes. Short for a 25-minute mission.
PARTIALLY_CHARGED = BatteryRecord(
    battery_id="BAT-002",
    state_of_charge=0.45,
    state_of_health=0.95,
    cycle_count=120,
    observed_at=OBSERVED_AT,
)

# Below the minimum launch charge fraction regardless of mission length.
NEARLY_FLAT = BatteryRecord(
    battery_id="BAT-003",
    state_of_charge=0.12,
    state_of_health=0.95,
    cycle_count=140,
    observed_at=OBSERVED_AT,
)

# Near retirement on both cycles and health.
DEGRADED = BatteryRecord(
    battery_id="BAT-004",
    state_of_charge=0.90,
    state_of_health=0.62,
    cycle_count=780,
    observed_at=OBSERVED_AT,
)

# Health absent. The predictor must assume 1.0, record the assumption, and
# downgrade confidence rather than failing.
STATE_OF_HEALTH_MISSING = BatteryRecord(
    battery_id="BAT-005",
    state_of_charge=0.92,
    state_of_health=None,
    cycle_count=None,
    observed_at=OBSERVED_AT,
)

# Charge absent. Endurance cannot be computed at all -> UNAVAILABLE.
CHARGE_MISSING = BatteryRecord(
    battery_id="BAT-006",
    state_of_charge=None,
    state_of_health=0.95,
    cycle_count=60,
    observed_at=OBSERVED_AT,
)

# Older than the 24-hour battery staleness policy.
STALE = BatteryRecord(
    battery_id="BAT-007",
    state_of_charge=0.88,
    state_of_health=0.94,
    cycle_count=75,
    observed_at=OBSERVED_AT - timedelta(days=3),
)
