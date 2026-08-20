from datetime import datetime, timezone, timedelta
from typing import Any
from tools.route_airspace_compliance.request_response_schemas import NfzRecord
from tools.route_airspace_compliance.recurrence_schemas import (
    HourlyRepetition,
    DailyRepetition,
    Month,
    MonthlyRepetition,
    RecurringSchedule,
    SpecificDaysOfMonth,
    YearlyRepetition,
)


def _from_epoch_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _normalize_recurring_schedule(validity: dict[str, Any]) -> RecurringSchedule:
    recurring = validity["recurring"]
    unit = recurring["unit"]
    quantity = recurring["quantity"]
    first_start = _from_epoch_ms(validity["start_on"])
    recurrence_end = _from_epoch_ms(validity["end_on"])
    duration = timedelta(milliseconds=recurring["duration"])

    if unit == "hour":
        recurrence_pattern = HourlyRepetition(every_hours=quantity)
    elif unit == "day":
        recurrence_pattern = DailyRepetition(every_days=quantity)
    elif unit == "month":
        recurrence_pattern = MonthlyRepetition(
            date_selection=SpecificDaysOfMonth(days=(first_start.day,)),
            every_months=quantity)
    elif unit == "year":
        recurrence_pattern = YearlyRepetition(months=(Month(
            first_start.month),), date_selection=SpecificDaysOfMonth(days=(first_start.day,)), every_years=quantity)
    else:
        raise NotImplementedError(
            f"Garuda recurrence unit {unit!r} is not normalized")

    return RecurringSchedule(
        timezone="UTC",
        effective_from=first_start,
        effective_until=recurrence_end,
        duration=duration,
        recurrence_pattern=recurrence_pattern
    )


def normalize_nfz_records(raw_nfz: dict[str, Any]) -> list[NfzRecord]:
    records: list[NfzRecord] = []

    validity_entries = raw_nfz.get("validity", [])
    for validity in validity_entries:
        if validity.get("recurring") is None:
            valid_from = _from_epoch_ms(validity["start_on"])
            valid_until = _from_epoch_ms(validity["end_on"])
            recurring_schedule = None
        else:
            valid_from = None
            valid_until = None
            recurring_schedule = _normalize_recurring_schedule(validity)

        zone_type = (raw_nfz.get("restriction")
                     or raw_nfz.get("type") or "unknown")
        record = NfzRecord(
            nfz_id=raw_nfz["nfz_id"],
            name=raw_nfz["name"],
            zone_type=zone_type,
            minimum_altitude_m=raw_nfz.get("min_altitude", -1000),
            maximum_altitude_m=raw_nfz.get("altitude", 31767),
            valid_from=valid_from,
            valid_until=valid_until,
            recurring_schedule=recurring_schedule
        )
        records.append(record)

    return records
