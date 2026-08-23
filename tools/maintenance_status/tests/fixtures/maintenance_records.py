"""Drone references and service records.

No Plex endpoint supplies service records today, so the SERVICED_* fixtures
describe the shape the tool will handle once one exists. The realistic case
right now is NO_SERVICE_RECORDS: an empty list.
"""

from datetime import date

from tools.maintenance_status.request_response_schemas import DroneRef, ServiceRecord

KNOWN_DRONE = DroneRef(
    drone_id="DRONE-001",
    name="Falcon 1",
    serial_number="SN-0001",
    model="Matrice 4",
)

# Resolvable, but the model is not in the service plan table — so there is no
# interval to compare against and the tool must return NEEDS_INFO.
UNKNOWN_MODEL_DRONE = DroneRef(
    drone_id="DRONE-005",
    name="Falcon 5",
    serial_number="SN-0005",
    model="Prototype X",
)

# Plex gave only a drone_model_id, which the adapter could not map to a name.
NO_MODEL_DRONE = DroneRef(
    drone_id="DRONE-006",
    name="Falcon 6",
    serial_number="SN-0006",
    model=None,
)

# The state of the world today: no maintenance endpoint, so no records.
NO_SERVICE_RECORDS: list[ServiceRecord] = []

SERVICED_RECENTLY = [
    ServiceRecord(
        serviced_on=date(2026, 7, 30),
        service_type="basic",
        airframe_hours_at_service=1204.0,
    ),
]

# Calendar due date lands before "today" in the service tests, so this drives
# an OVERDUE on the calendar even when hours are low.
SERVICED_LONG_AGO = [
    ServiceRecord(
        serviced_on=date(2025, 1, 10),
        service_type="major",
        airframe_hours_at_service=880.0,
    ),
]

# Two services, out of order, to prove the latest one wins.
MULTIPLE_SERVICES = [
    ServiceRecord(serviced_on=date(2025, 11, 2), service_type="basic"),
    ServiceRecord(serviced_on=date(2026, 7, 30), service_type="major"),
    ServiceRecord(serviced_on=date(2026, 2, 14), service_type="basic"),
]
