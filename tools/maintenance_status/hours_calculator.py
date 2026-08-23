"""Sum flight hours for a drone.

Plex has no aggregated airframe-hours field, so hours are summed client-side
from Flight records. The confirmed payload shape reports duration as a
{hours, minutes, seconds} object rather than start and end timestamps, so
there are no deltas to compute — the durations are added directly.

`hours_source` on the result records which path produced the number, so a
reviewer can tell an aggregated Plex figure from a computed one. Both values
are kept in one place here rather than spelled as literals at the call site.

Pure. No I/O, no clock.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from tools.maintenance_status.request_response_schemas import FlightRecord

SOURCE_PLEX_AGGREGATE = "plex_aggregate"
SOURCE_COMPUTED = "computed_from_flight_records"

SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True)
class HoursResult:
    hours: float
    source: str
    flights_counted: int
    flights_skipped: int = 0


def sum_flight_hours(
    records: list[FlightRecord] | tuple[FlightRecord, ...],
    *,
    since: date | None = None,
) -> HoursResult:
    """Total flight hours, optionally only counting flights after a service.

    A flight with no duration is skipped rather than counted as zero, and the
    skip is reported: silently treating a missing duration as zero would
    understate airframe hours, which is the direction that hides an overdue
    airframe.

    A flight with no date is still counted when `since` is None. When `since`
    is given it is skipped, because it cannot be placed relative to the
    service — undercounting there is the conservative error in the other
    direction, so it is reported too.
    """
    total_seconds = 0.0
    counted = 0
    skipped = 0

    for record in records or ():
        if record.duration_seconds is None or record.duration_seconds < 0:
            skipped += 1
            continue

        if since is not None:
            if record.flown_on is None:
                skipped += 1
                continue
            if _as_date(record.flown_on) <= since:
                continue

        total_seconds += record.duration_seconds
        counted += 1

    return HoursResult(
        hours=round(total_seconds / SECONDS_PER_HOUR, 2),
        source=SOURCE_COMPUTED,
        flights_counted=counted,
        flights_skipped=skipped,
    )


def hours_from_aggregate(value: float) -> HoursResult:
    """Wrap an aggregated Plex airframe-hours figure, when one ever exists."""
    return HoursResult(
        hours=round(float(value), 2),
        source=SOURCE_PLEX_AGGREGATE,
        flights_counted=0,
    )


def _as_date(value: datetime | date) -> date:
    if isinstance(value, datetime):
        # Compare in a fixed zone so a flight logged late in the day is not
        # pushed either side of the service date by the reader's timezone.
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.date()
    return value


def duration_seconds_from_parts(duration: object) -> float | None:
    """Flatten Plex's {hours, minutes, seconds} duration object into seconds."""
    if not isinstance(duration, dict):
        return None
    try:
        return (
            float(duration.get("hours") or 0) * 3600.0
            + float(duration.get("minutes") or 0) * 60.0
            + float(duration.get("seconds") or 0)
        )
    except (TypeError, ValueError):
        return None


def epoch_ms_to_datetime(value: object) -> datetime | None:
    """Plex reports a flight date as epoch milliseconds, or -1 when unset."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def combine(day: date) -> datetime:
    """Midnight UTC on a date, for comparing a service date against flights."""
    return datetime.combine(day, time.min, tzinfo=timezone.utc)
