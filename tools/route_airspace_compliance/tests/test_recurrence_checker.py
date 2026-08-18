import pytest
from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from tools.route_airspace_compliance.checkers.recurrence_checker import recurring_schedule_overlaps
from tools.route_airspace_compliance.recurrence_schemas import DailyRepetition, RecurringSchedule

SINGAPORE_TIMEZONE = ZoneInfo("Asia/Singapore")

BASE_DAILY_SCHEDULE = RecurringSchedule(
    timezone="Asia/Singapore",
    effective_from=date(2026, 8, 1),
    start_time=time(15, 0),
    end_time=time(18, 0),
    recurrence_pattern=DailyRepetition(),
)

def overlaps_on_august_day(
    schedule: RecurringSchedule,
    day: int,
    start_hour: int = 16,
    end_hour: int = 17,
) -> bool:
    return recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, day, start_hour,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, day, end_hour,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

def test_daily_schedule_overlaps_flight_during_active_hours() -> None:
    singapore_timezone = ZoneInfo("Asia/Singapore")
    schedule = RecurringSchedule(
        timezone="Asia/Singapore",
        effective_from=date(2026, 8, 1),
        start_time=time(15, 0),
        end_time=time(18, 0),
        recurrence_pattern=DailyRepetition(),
    )
    result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 15, 16, 0,
            tzinfo=singapore_timezone,
        ),
        planned_end_time=datetime(
            2026, 8, 15, 17, 0,
            tzinfo=singapore_timezone,
        ),
    )
    assert result is True
    
def test_daily_schedule_checks_next_day_when_flight_crosses_midnight() -> None:
    singapore_timezone = ZoneInfo("Asia/Singapore")
    schedule = RecurringSchedule(
        timezone="Asia/Singapore",
        effective_from=date(2026, 8, 1),
        start_time=time(15, 0),
        end_time=time(18, 0),
        recurrence_pattern=DailyRepetition(),
    )
    result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 15, 19, 0,
            tzinfo=singapore_timezone,
        ),
        planned_end_time=datetime(
            2026, 8, 16, 16, 0,
            tzinfo=singapore_timezone,
        ),
    )
    assert result is True
    
def test_daily_schedule_does_not_overlap_outside_active_hours() -> None:
    singapore_timezone = ZoneInfo("Asia/Singapore")
    schedule = RecurringSchedule(
        timezone="Asia/Singapore",
        effective_from=date(2026, 8, 1),
        start_time=time(15, 0),
        end_time=time(18, 0),
        recurrence_pattern=DailyRepetition(),
    )
    result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 15, 19, 0,
            tzinfo=singapore_timezone,
        ),
        planned_end_time=datetime(
            2026, 8, 15, 20, 0,
            tzinfo=singapore_timezone,
        ),
    )
    assert result is False
    
def test_daily_schedule_respects_every_days_interval() -> None:
    singapore_timezone = ZoneInfo("Asia/Singapore")
    schedule = RecurringSchedule(
        timezone="Asia/Singapore",
        effective_from=date(2026, 8, 1),
        start_time=time(15, 0),
        end_time=time(18, 0),
        recurrence_pattern=DailyRepetition(every_days=2),
    )
    active_result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 15, 16, 0,
            tzinfo=singapore_timezone,
        ),
        planned_end_time=datetime(
            2026, 8, 15, 17, 0,
            tzinfo=singapore_timezone,
        ),
    )
    inactive_result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 16, 16, 0,
            tzinfo=singapore_timezone,
        ),
        planned_end_time=datetime(
            2026, 8, 16, 17, 0,
            tzinfo=singapore_timezone,
        ),
    )
    assert active_result is True
    assert inactive_result is False
    
def test_daily_schedule_does_not_activate_on_excluded_date() -> None:
    singapore_timezone = ZoneInfo("Asia/Singapore")
    schedule = RecurringSchedule(
        timezone="Asia/Singapore",
        effective_from=date(2026, 8, 1),
        start_time=time(15, 0),
        end_time=time(18, 0),
        recurrence_pattern=DailyRepetition(),
        excluded_dates=(date(2026, 8, 15),),
    )
    result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 15, 16, 0,
            tzinfo=singapore_timezone,
        ),
        planned_end_time=datetime(
            2026, 8, 15, 17, 0,
            tzinfo=singapore_timezone,
        ),
    )
    assert result is False
    
def test_daily_schedule_respects_effective_date_range() -> None:
    schedule = replace(
        BASE_DAILY_SCHEDULE,
        effective_from=date(2026, 8, 10),
        effective_until=date(2026, 8, 20),
    )
    assert overlaps_on_august_day(schedule, 9) is False
    assert overlaps_on_august_day(schedule, 10) is True
    assert overlaps_on_august_day(schedule, 20) is True
    assert overlaps_on_august_day(schedule, 21) is False
    
def test_daily_schedule_treats_touching_boundaries_as_overlap() -> None:
    ends_when_nfz_starts = overlaps_on_august_day(
        BASE_DAILY_SCHEDULE,
        day=15,
        start_hour=14,
        end_hour=15,
    )
    starts_when_nfz_ends = overlaps_on_august_day(
        BASE_DAILY_SCHEDULE,
        day=15,
        start_hour=18,
        end_hour=19,
    )
    assert ends_when_nfz_starts is True
    assert starts_when_nfz_ends is True
    
def test_daily_schedule_converts_flight_into_schedule_timezone() -> None:
    utc_timezone = ZoneInfo("UTC")
    result = recurring_schedule_overlaps(
        schedule=BASE_DAILY_SCHEDULE,
        planned_start_time=datetime(
            2026, 8, 15, 8, 0,
            tzinfo=utc_timezone,
        ),
        planned_end_time=datetime(
            2026, 8, 15, 9, 0,
            tzinfo=utc_timezone,
        ),
    )
    assert result is True
    
def test_daily_schedule_rejects_non_positive_interval() -> None:
    schedule = replace(
        BASE_DAILY_SCHEDULE,
        recurrence_pattern=DailyRepetition(
            every_days=0,
        ),
    )
    with pytest.raises(ValueError, match="every_days"):
        overlaps_on_august_day(schedule, 15)

def test_daily_schedule_rejects_empty_activation_window() -> None:
    schedule = replace(
        BASE_DAILY_SCHEDULE,
        start_time=time(18, 0),
        end_time=time(18, 0),
    )
    with pytest.raises(ValueError, match="Overnight recurring schedules",):
        overlaps_on_august_day(schedule, 15)
        
def test_daily_schedule_rejects_unknown_timezone() -> None:
    schedule = replace(
        BASE_DAILY_SCHEDULE,
        timezone="Not/A-Real-Timezone",
    )
    with pytest.raises(ValueError, match="timezone"):
        overlaps_on_august_day(schedule, 15)
        
def test_daily_schedule_rejects_naive_flight_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        recurring_schedule_overlaps(
            schedule=BASE_DAILY_SCHEDULE,
            planned_start_time=datetime(
                2026, 8, 15, 16, 0,
            ),
            planned_end_time=datetime(
                2026, 8, 15, 17, 0,
            ),
        )
        
def test_daily_schedule_rejects_reversed_flight_window() -> None:
    with pytest.raises(ValueError, match="planned_end_time"):
        recurring_schedule_overlaps(
            schedule=BASE_DAILY_SCHEDULE,
            planned_start_time=datetime(
                2026, 8, 15, 17, 0,
                tzinfo=SINGAPORE_TIMEZONE,
            ),
            planned_end_time=datetime(
                2026, 8, 15, 16, 0,
                tzinfo=SINGAPORE_TIMEZONE,
            ),
        )
        
def test_daily_schedule_rejects_reversed_effective_range() -> None:
    schedule = replace(
        BASE_DAILY_SCHEDULE,
        effective_from=date(2026, 8, 20),
        effective_until=date(2026, 8, 10),
    )
    with pytest.raises(ValueError, match="effective_until"):
        overlaps_on_august_day(schedule, 15)