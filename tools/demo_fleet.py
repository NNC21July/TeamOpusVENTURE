"""A seeded fleet for demonstrating the tools without a live Aircraft Service.

Why this exists: as of 30 Aug the Garuda Aircraft Service authenticates and
answers /aircraft/sanity, but every data endpoint returns HTTP 504 or times
out. Weather is unaffected and stays genuinely live. This module supplies the
Plex half so the decision logic can be shown end to end.

This is SIMULATED DATA and every response built from it says so. It is not a
mock in the testing sense — it is a demonstration fixture, deliberately shaped
so the four interesting outcomes are all reachable:

    Drone A   freshly serviced, healthy battery      -> GO
    Drone B   inside the service warning band        -> GO_WITH_WARNINGS
    Drone C   past its service interval              -> NO_GO
    Drone D   not ready to fly, low battery          -> NO_GO

Enable with GARUDA_DEMO_MODE=1. The real clients are used otherwise.
"""

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

SIMULATED_NOTICE = (
    "SIMULATED FLEET DATA. The Garuda Aircraft Service was unreachable, so "
    "drone, flight and maintenance records are seeded demonstration values. "
    "Weather in this assessment is live and real."
)

ENV_FLAG = "GARUDA_DEMO_MODE"

# One 40-minute sortie, the tempo the seeded flight history is built from.
SORTIE_SECONDS = 40 * 60


def demo_mode_enabled() -> bool:
    return os.getenv(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DemoDrone:
    drone_id: str
    name: str
    serial_number: str
    model: str
    status: str
    serviceable: bool
    is_flying: bool
    state_of_charge: float
    state_of_health: float
    cycle_count: int
    # Sorties flown since the last service; drives hours-since-service.
    sorties_since_service: int
    last_service_date: date
    last_service_type: str
    service_interval_hours: float
    service_interval_months: int


# A 200 hour / 6 month interval, matching the local specs table so the demo is
# self-consistent. The shared tool contract's worked example uses 100 hours.
_INTERVAL_HOURS = 200.0
_INTERVAL_MONTHS = 6

FLEET: tuple[DemoDrone, ...] = (
    DemoDrone(
        drone_id="0ba2c40dca916d1eb4414d1fbe03937b",
        name="NTU Sim Drone A",
        serial_number="NTU-SIM_1CDD47",
        model="Matrice 4",
        status="RTF",
        serviceable=True,
        is_flying=False,
        state_of_charge=0.95,
        state_of_health=0.98,
        cycle_count=42,
        sorties_since_service=63,      # 42.0 h  -> OK
        last_service_date=date(2026, 7, 30),
        last_service_type="100h inspection",
        service_interval_hours=_INTERVAL_HOURS,
        service_interval_months=_INTERVAL_MONTHS,
    ),
    DemoDrone(
        drone_id="1cb3d51eda927e2fc5525e2gcf14a48c",
        name="NTU Sim Drone B",
        serial_number="NTU-SIM_2DEE58",
        model="Matrice 4",
        status="RTF",
        serviceable=True,
        is_flying=False,
        state_of_charge=0.88,
        state_of_health=0.94,
        cycle_count=210,
        sorties_since_service=274,     # 182.7 h -> DUE_SOON
        last_service_date=date(2026, 7, 1),
        last_service_type="basic",
        service_interval_hours=_INTERVAL_HOURS,
        service_interval_months=_INTERVAL_MONTHS,
    ),
    DemoDrone(
        drone_id="2dc4e62feb038f3gd6636f3hdg25b59d",
        name="NTU Sim Drone C",
        serial_number="NTU-SIM_3EFF69",
        model="Matrice 4",
        status="RTF",
        serviceable=True,
        is_flying=False,
        state_of_charge=0.91,
        state_of_health=0.90,
        cycle_count=340,
        sorties_since_service=322,     # 214.7 h -> OVERDUE
        last_service_date=date(2026, 6, 1),
        last_service_type="basic",
        service_interval_hours=_INTERVAL_HOURS,
        service_interval_months=_INTERVAL_MONTHS,
    ),
    DemoDrone(
        drone_id="3ed5f73gfc149g4he7747g4ieh36c60e",
        name="NTU Sim Drone D",
        serial_number="NTU-SIM_4FGG70",
        model="Matrice 4",
        status="INIT",                 # not ready to fly -> NO_GO
        serviceable=True,
        is_flying=False,
        state_of_charge=0.18,          # also below minimum launch charge
        state_of_health=0.85,
        cycle_count=95,
        sorties_since_service=10,
        last_service_date=date(2026, 8, 20),
        last_service_type="basic",
        service_interval_hours=_INTERVAL_HOURS,
        service_interval_months=_INTERVAL_MONTHS,
    ),
)


def find(identifier: str) -> DemoDrone | None:
    """Resolve a drone by name, serial or id, the way a pilot would say it."""
    if not identifier or not identifier.strip():
        return None
    needle = identifier.strip().casefold()
    for drone in FLEET:
        for value in (drone.name, drone.serial_number, drone.drone_id):
            if value.casefold() == needle:
                return drone
    # Also accept a bare letter, so "drone A" and "A" both work on stage.
    for drone in FLEET:
        if drone.name.casefold().endswith(needle):
            return drone
    return None


def flight_durations(drone: DemoDrone, *, now: datetime | None = None):
    """Seeded sorties for a drone, most recent last.

    Spread evenly across the window between the last service and now, so that
    every sortie counts toward hours-since-service. A fixed weekly tempo would
    push most of them before the service date, where they would be correctly
    excluded and the demo would understate hours.
    """
    ending = now or datetime.now(timezone.utc)
    # The day AFTER the service, not the day of it: the hours calculator counts
    # only flights strictly after a service date, so sorties seeded on the
    # service day itself would be correctly excluded and the seeded count would
    # not match the hours the demo reports.
    start = datetime.combine(
        drone.last_service_date, datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(days=1)

    count = drone.sorties_since_service
    if count <= 0:
        return

    window = ending - start
    if window <= timedelta(0):
        window = timedelta(days=1)

    step = window / (count + 1)
    for index in range(count):
        yield (
            f"FLT-{drone.serial_number[-4:]}-{index:04d}",
            start + step * (index + 1),
            float(SORTIE_SECONDS),
        )
