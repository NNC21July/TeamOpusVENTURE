"""Flight records for the hours calculator.

Shaped to the confirmed Plex payload: duration arrives as a
{hours, minutes, seconds} object and the date as epoch milliseconds, both
already flattened here into what the calculator consumes.

A realistic weekly tempo, since the sandbox has no operational data:
roughly two 40-minute sorties a week.
"""

from datetime import datetime, timedelta, timezone

from tools.maintenance_status.request_response_schemas import FlightRecord

UTC = timezone.utc
TODAY = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)

SORTIE_SECONDS = 40 * 60  # 40 minutes


def weekly_tempo(count: int, *, ending: datetime = TODAY) -> list[FlightRecord]:
    """`count` sorties at roughly two a week, most recent last."""
    records: list[FlightRecord] = []
    for index in range(count):
        flown = ending - timedelta(days=3.5 * (count - index))
        records.append(
            FlightRecord(
                flight_id=f"FLT-{index:04d}",
                drone_name="Falcon 1",
                status="postflight",
                flown_on=flown,
                duration_seconds=SORTIE_SECONDS,
            )
        )
    return records


# 63 sorties x 40 min = 42.0 hours. Comfortably inside a 200 hour interval.
FRESHLY_SERVICED = weekly_tempo(63)

# 274 sorties x 40 min = 182.67 hours. Inside the 10% warning band of 200.
NEAR_SERVICE_INTERVAL = weekly_tempo(274)

# 310 sorties x 40 min = 206.67 hours. Past the interval.
PAST_SERVICE_INTERVAL = weekly_tempo(310)

NO_FLIGHTS: list[FlightRecord] = []

# Duration absent. Must be skipped and reported, never counted as zero:
# silently zeroing understates airframe hours, which hides an overdue frame.
MISSING_DURATION = [
    FlightRecord(
        flight_id="FLT-9001",
        drone_name="Falcon 1",
        status="postflight",
        flown_on=TODAY - timedelta(days=2),
        duration_seconds=None,
    ),
    FlightRecord(
        flight_id="FLT-9002",
        drone_name="Falcon 1",
        status="postflight",
        flown_on=TODAY - timedelta(days=5),
        duration_seconds=SORTIE_SECONDS,
    ),
]

# Plex reports -1 for a flight with no date set, which becomes None here.
MISSING_DATE = [
    FlightRecord(
        flight_id="FLT-9003",
        drone_name="Falcon 1",
        status="postflight",
        flown_on=None,
        duration_seconds=SORTIE_SECONDS,
    ),
]

# Flights for a different airframe, to prove filtering by drone name works.
OTHER_DRONE = [
    FlightRecord(
        flight_id="FLT-8001",
        drone_name="Falcon 2",
        status="postflight",
        flown_on=TODAY - timedelta(days=1),
        duration_seconds=SORTIE_SECONDS,
    ),
]
