"""Demo AircraftClient backed by the seeded fleet.

Satisfies the same protocol as GarudaAircraftClient. Operating limits come
from the local specs table, exactly as they would for a real drone whose model
Plex does not describe — so the demo exercises the same code path, and the
output still says the limits were locally sourced.
"""

from datetime import datetime, timedelta, timezone

from tools import demo_fleet
from tools.flight_readiness.client_protocol import DroneNotFoundError
from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    BatteryRecord,
)
from tools.flight_readiness.specs.model_limits import get_model_limits


class DemoAircraftClient:
    """Serves seeded aircraft and battery state."""

    def __init__(self, *, now: datetime | None = None) -> None:
        self._now = now or datetime.now(timezone.utc)

    def get_aircraft(self, *, drone: str) -> AircraftRecord:
        found = demo_fleet.find(drone)
        if found is None:
            known = ", ".join(d.name for d in demo_fleet.FLEET)
            raise DroneNotFoundError(
                f"No drone matching {drone!r} in the demonstration fleet. "
                f"Known drones: {known}."
            )

        limits = get_model_limits(found.model)
        return AircraftRecord(
            drone_id=found.drone_id,
            model=found.model,
            status=found.status,
            name=found.name,
            max_wind_resistance_ms=limits.max_wind_resistance_ms if limits else None,
            max_flight_time_min=limits.max_flight_time_min if limits else None,
            operating_temp_min_c=limits.operating_temp_min_c if limits else None,
            operating_temp_max_c=limits.operating_temp_max_c if limits else None,
            precipitation_tolerance_mm_h=(
                limits.precipitation_tolerance_mm_h if limits else None
            ),
            is_flying=found.is_flying,
            serviceable=found.serviceable,
            limits_source="local_specs" if limits else None,
            # Recent enough not to trip the staleness policy, so confidence in
            # the demo is driven by forecast horizon rather than stale data.
            observed_at=self._now - timedelta(minutes=5),
        )

    def get_battery(self, *, drone_id: str) -> BatteryRecord:
        found = demo_fleet.find(drone_id)
        if found is None:
            raise DroneNotFoundError(f"No drone {drone_id!r} in the demonstration fleet")
        return BatteryRecord(
            battery_id=f"BAT-{found.serial_number[-4:]}",
            state_of_charge=found.state_of_charge,
            state_of_health=found.state_of_health,
            cycle_count=found.cycle_count,
            observed_at=self._now - timedelta(minutes=5),
        )
