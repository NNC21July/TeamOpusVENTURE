from datetime import datetime, timedelta, timezone

from tools.route_airspace_compliance.garuda_airspace_adapter import normalize_nfz_records
from tools.route_airspace_compliance.recurrence_schemas import (
    DailyRepetition,
    HourlyRepetition,
    Month,
    MonthlyRepetition,
    SpecificDaysOfMonth,
    YearlyRepetition,
)


def test_normalizes_non_recurring_garuda_nfz() -> None:
    start_time = datetime(2026, 8, 10, 1, 0, tzinfo=timezone.utc)
    end_time = datetime(2026, 8, 10, 2, 0, tzinfo=timezone.utc)
    raw_nfz = {
        "nfz_id": "GARUDA-NFZ-001",
        "type": "temp",
        "restriction": "aerodrome",
        "status": "active",
        "name": "Test Aerodrome",
        "min_altitude": 0,
        "altitude": 120,
        "altitude_reference": "WGS84",
        "validity": [
            {
                "start_on": int(start_time.timestamp() * 1000),
                "end_on": int(end_time.timestamp() * 1000),
            }
        ],
    }
    records = normalize_nfz_records(raw_nfz)
    assert len(records) == 1
    record = records[0]
    assert record.nfz_id == "GARUDA-NFZ-001"
    assert record.name == "Test Aerodrome"
    assert record.zone_type == "aerodrome"
    assert record.minimum_altitude_m == 0
    assert record.maximum_altitude_m == 120
    assert record.valid_from == start_time
    assert record.valid_until == end_time
    assert record.recurring_schedule is None


def test_uses_garuda_altitude_defaults_when_fields_are_missing() -> None:
    start_time = datetime(2026, 8, 10, 1, 0, tzinfo=timezone.utc)
    end_time = datetime(2026, 8, 10, 2, 0, tzinfo=timezone.utc)
    raw_nfz = {
        "nfz_id": "GARUDA-NFZ-002",
        "type": "static",
        "restriction": "military properties",
        "status": "active",
        "name": "Test Military Area",
        "validity": [
            {
                "start_on": int(start_time.timestamp() * 1000),
                "end_on": int(end_time.timestamp() * 1000),
            }
        ],
    }
    record = normalize_nfz_records(raw_nfz)[0]
    assert record.minimum_altitude_m == -1000
    assert record.maximum_altitude_m == 31767


def test_creates_one_record_for_each_validity_entry() -> None:
    first_start = datetime(2026, 8, 10, 1, 0, tzinfo=timezone.utc)
    first_end = datetime(2026, 8, 10, 2, 0, tzinfo=timezone.utc)
    second_start = datetime(2026, 8, 11, 1, 0, tzinfo=timezone.utc)
    second_end = datetime(2026, 8, 11, 2, 0, tzinfo=timezone.utc)
    raw_nfz = {
        "nfz_id": "GARUDA-NFZ-003",
        "type": "temp",
        "restriction": "protected-area",
        "status": "active",
        "name": "Test Protected Area",
        "min_altitude": 0,
        "altitude": 100,
        "validity": [
            {
                "start_on": int(first_start.timestamp() * 1000),
                "end_on": int(first_end.timestamp() * 1000),
            },
            {
                "start_on": int(second_start.timestamp() * 1000),
                "end_on": int(second_end.timestamp() * 1000),
            },
        ],
    }
    records = normalize_nfz_records(raw_nfz)
    assert len(records) == 2
    assert records[0].nfz_id == "GARUDA-NFZ-003"
    assert records[0].valid_from == first_start
    assert records[0].valid_until == first_end
    assert records[1].nfz_id == "GARUDA-NFZ-003"
    assert records[1].valid_from == second_start
    assert records[1].valid_until == second_end


def test_normalizes_daily_recurring_garuda_nfz() -> None:
    first_start = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
    recurrence_end = datetime(2026, 8, 31, 10, 15, tzinfo=timezone.utc)
    three_hours_ms = 3 * 60 * 60 * 1000
    raw_nfz = {
        "nfz_id": "GARUDA-NFZ-004",
        "type": "temp",
        "restriction": "aerodrome",
        "status": "active",
        "name": "Daily Test Aerodrome",
        "min_altitude": 0,
        "altitude": 120,
        "validity": [
            {
                "start_on": int(first_start.timestamp() * 1000),
                "end_on": int(recurrence_end.timestamp() * 1000),
                "recurring": {
                    "duration": three_hours_ms,
                    "quantity": 1,
                    "unit": "day",
                },
            }
        ],
    }
    record = normalize_nfz_records(raw_nfz)[0]
    assert record.valid_from is None
    assert record.valid_until is None
    assert record.recurring_schedule is not None
    assert record.recurring_schedule.timezone == "UTC"
    assert record.recurring_schedule.effective_from == first_start
    assert record.recurring_schedule.effective_until == recurrence_end
    assert record.recurring_schedule.duration == timedelta(hours=3)
    assert record.recurring_schedule.recurrence_pattern == DailyRepetition(
        every_days=1
    )


def test_normalizes_every_seven_days_garuda_recurrence() -> None:
    first_start = datetime(2026, 8, 14, 15, 0, tzinfo=timezone.utc)
    recurrence_end = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)
    raw_nfz = {
        "nfz_id": "GARUDA-NFZ-005",
        "type": "temp",
        "restriction": "temporary-restricted-area",
        "status": "active",
        "name": "Weekly Test Area",
        "validity": [
            {
                "start_on": int(first_start.timestamp() * 1000),
                "end_on": int(recurrence_end.timestamp() * 1000),
                "recurring": {
                    "duration": 3 * 60 * 60 * 1000,
                    "quantity": 7,
                    "unit": "day",
                },
            }
        ],
    }
    record = normalize_nfz_records(raw_nfz)[0]
    assert record.recurring_schedule is not None
    assert record.recurring_schedule.recurrence_pattern == DailyRepetition(
        every_days=7
    )


def test_normalizes_monthly_garuda_recurrence() -> None:
    first_start = datetime(2026, 8, 18, 15, 0, tzinfo=timezone.utc)
    recurrence_end = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)
    raw_nfz = {
        "nfz_id": "GARUDA-NFZ-006",
        "type": "temp",
        "restriction": "temporary-restricted-area",
        "status": "active",
        "name": "Monthly Test Area",
        "validity": [
            {
                "start_on": int(first_start.timestamp() * 1000),
                "end_on": int(recurrence_end.timestamp() * 1000),
                "recurring": {
                    "duration": 3 * 60 * 60 * 1000,
                    "quantity": 1,
                    "unit": "month",
                },
            }
        ],
    }
    record = normalize_nfz_records(raw_nfz)[0]
    assert record.recurring_schedule is not None
    assert record.recurring_schedule.recurrence_pattern == MonthlyRepetition(
        date_selection=SpecificDaysOfMonth(days=(18,)),
        every_months=1,
    )


def test_normalizes_yearly_garuda_recurrence() -> None:
    first_start = datetime(2026, 8, 18, 15, 0, tzinfo=timezone.utc)
    recurrence_end = datetime(2034, 12, 31, 23, 59, tzinfo=timezone.utc)
    raw_nfz = {
        "nfz_id": "GARUDA-NFZ-007",
        "type": "temp",
        "restriction": "temporary-restricted-area",
        "status": "active",
        "name": "Yearly Test Area",
        "validity": [
            {
                "start_on": int(first_start.timestamp() * 1000),
                "end_on": int(recurrence_end.timestamp() * 1000),
                "recurring": {
                    "duration": 3 * 60 * 60 * 1000,
                    "quantity": 2,
                    "unit": "year",
                },
            }
        ],
    }
    record = normalize_nfz_records(raw_nfz)[0]
    assert record.recurring_schedule is not None
    assert record.recurring_schedule.recurrence_pattern == YearlyRepetition(
        months=(Month.AUGUST,),
        date_selection=SpecificDaysOfMonth(days=(18,)),
        every_years=2,
    )


def test_normalizes_hourly_garuda_recurrence() -> None:
    first_start = datetime(2026, 8, 18, 15, 0, tzinfo=timezone.utc)
    recurrence_end = datetime(2026, 8, 19, 23, 59, tzinfo=timezone.utc)
    raw_nfz = {
        "nfz_id": "GARUDA-NFZ-008",
        "type": "temp",
        "restriction": "temporary-restricted-area",
        "status": "active",
        "name": "Hourly Test Area",
        "validity": [
            {
                "start_on": int(first_start.timestamp() * 1000),
                "end_on": int(recurrence_end.timestamp() * 1000),
                "recurring": {
                    "duration": 30 * 60 * 1000,
                    "quantity": 1,
                    "unit": "hour",
                },
            }
        ],
    }

    record = normalize_nfz_records(raw_nfz)[0]
    assert record.recurring_schedule is not None
    assert record.recurring_schedule.effective_from == first_start
    assert record.recurring_schedule.effective_until == recurrence_end
    assert record.recurring_schedule.duration == timedelta(minutes=30)
    assert record.recurring_schedule.recurrence_pattern == HourlyRepetition(
        every_hours=1,
    )


def test_normalizes_recurring_duration_that_crosses_midnight() -> None:
    first_start = datetime(2026, 8, 18, 22, 0, tzinfo=timezone.utc)
    recurrence_end = datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc)
    raw_nfz = {
        "nfz_id": "GARUDA-NFZ-009",
        "type": "temp",
        "restriction": "temporary-restricted-area",
        "status": "active",
        "name": "Overnight Test Area",
        "validity": [
            {
                "start_on": int(first_start.timestamp() * 1000),
                "end_on": int(recurrence_end.timestamp() * 1000),
                "recurring": {
                    "duration": 4 * 60 * 60 * 1000,
                    "quantity": 1,
                    "unit": "day",
                },
            }
        ],
    }

    record = normalize_nfz_records(raw_nfz)[0]
    assert record.recurring_schedule is not None
    assert record.recurring_schedule.effective_from == first_start
    assert record.recurring_schedule.effective_until == recurrence_end
    assert record.recurring_schedule.duration == timedelta(hours=4)
