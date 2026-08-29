"""Demo MaintenanceClient backed by the seeded fleet.

Satisfies the same protocol as GarudaMaintenanceClient, so the service layer
cannot tell the difference — which is the point of the protocol. Selected by
GARUDA_DEMO_MODE=1 when the Aircraft Service is unreachable.
"""

from datetime import datetime, timezone

from tools import demo_fleet
from tools.maintenance_status.client_protocol import DroneNotFoundError
from tools.maintenance_status.request_response_schemas import (
    DroneRef,
    FlightRecord,
    ServicePlan,
    ServiceRecord,
)

DEMO_SOURCE = "demo_fleet"


class DemoMaintenanceClient:
    """Serves seeded drone, flight and maintenance records."""

    def __init__(self, *, now: datetime | None = None) -> None:
        self._now = now or datetime.now(timezone.utc)

    def get_drone(self, *, drone: str) -> DroneRef:
        found = demo_fleet.find(drone)
        if found is None:
            known = ", ".join(d.name for d in demo_fleet.FLEET)
            raise DroneNotFoundError(
                f"No drone matching {drone!r} in the demonstration fleet. "
                f"Known drones: {known}."
            )
        return DroneRef(
            drone_id=found.drone_id,
            name=found.name,
            serial_number=found.serial_number,
            model=found.model,
        )

    def get_flight_records(self, *, drone: DroneRef) -> list[FlightRecord]:
        found = demo_fleet.find(drone.drone_id)
        if found is None:
            return []
        return [
            FlightRecord(
                flight_id=flight_id,
                drone_name=found.name,
                status="postflight",
                flown_on=flown_on,
                duration_seconds=seconds,
            )
            for flight_id, flown_on, seconds in demo_fleet.flight_durations(
                found, now=self._now
            )
        ]

    def get_service_records(self, *, drone: DroneRef) -> list[ServiceRecord]:
        found = demo_fleet.find(drone.drone_id)
        if found is None:
            return []
        return [
            ServiceRecord(
                serviced_on=found.last_service_date,
                service_type=found.last_service_type,
            )
        ]

    def get_service_plan(self, *, drone: DroneRef) -> ServicePlan | None:
        found = demo_fleet.find(drone.drone_id)
        if found is None:
            return None
        return ServicePlan(
            model=found.model,
            interval_hours=found.service_interval_hours,
            interval_months=found.service_interval_months,
            plan_name="Demonstration service plan",
            source=DEMO_SOURCE,
        )
