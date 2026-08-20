import pytest
from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from tools.route_airspace_compliance.checkers.recurrence_checker import recurring_schedule_overlaps
from tools.route_airspace_compliance.recurrence_schemas import (
    DailyRepetition,
    HourlyRepetition,
    Month,
    MonthlyRepetition,
    NthWeekdayOfMonth,
    RecurringSchedule,
    SpecificDaysOfMonth,
    Weekday,
    WeekPosition,
    WeeklyRepetition,
    YearlyRepetition,
)

SINGAPORE_TIMEZONE = ZoneInfo("Asia/Singapore")


def singapore_end_of_day(year: int, month: int, day: int) -> datetime:
    return datetime(
        year,
        month,
        day,
        23,
        59,
        59,
        999999,
        tzinfo=SINGAPORE_TIMEZONE,
    )


BASE_HOURLY_SCHEDULE = RecurringSchedule(
    timezone="Asia/Singapore",
    effective_from=datetime(
        2026, 8, 18, 15, 0,
        tzinfo=SINGAPORE_TIMEZONE,
    ),
    duration=timedelta(minutes=30),
    recurrence_pattern=HourlyRepetition(),
    effective_until=singapore_end_of_day(2026, 8, 19),
)

BASE_DAILY_SCHEDULE = RecurringSchedule(
    timezone="Asia/Singapore",
    effective_from=datetime(
        2026, 8, 1, 15, 0,
        tzinfo=SINGAPORE_TIMEZONE,
    ),
    duration=timedelta(hours=3),
    recurrence_pattern=DailyRepetition(),
)

BASE_WEEKLY_SCHEDULE = RecurringSchedule(
    timezone="Asia/Singapore",
    effective_from=datetime(
        2026, 8, 3, 15, 0,
        tzinfo=SINGAPORE_TIMEZONE,
    ),
    duration=timedelta(hours=3),
    recurrence_pattern=WeeklyRepetition(
        days_of_week=(
            Weekday.MONDAY,
            Weekday.WEDNESDAY,
            Weekday.FRIDAY,
        ),
    ),
)

BASE_MONTHLY_SCHEDULE = RecurringSchedule(
    timezone="Asia/Singapore",
    effective_from=datetime(
        2026, 1, 1, 15, 0,
        tzinfo=SINGAPORE_TIMEZONE,
    ),
    duration=timedelta(hours=3),
    recurrence_pattern=MonthlyRepetition(
        date_selection=SpecificDaysOfMonth(
            days=(18, 21, 23),
        ),
    ),
)

BASE_YEARLY_SCHEDULE = RecurringSchedule(
    timezone="Asia/Singapore",
    effective_from=datetime(
        2026, 1, 1, 15, 0,
        tzinfo=SINGAPORE_TIMEZONE,
    ),
    duration=timedelta(hours=3),
    recurrence_pattern=YearlyRepetition(
        months=(Month.AUGUST, Month.OCTOBER),
        date_selection=SpecificDaysOfMonth(
            days=(18, 21),
        ),
    ),
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

def overlaps_on_date(
    schedule: RecurringSchedule,
    flight_date: date,
    start_hour: int = 16,
    end_hour: int = 17,
) -> bool:
    return recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            flight_date.year,
            flight_date.month,
            flight_date.day,
            start_hour,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            flight_date.year,
            flight_date.month,
            flight_date.day,
            end_hour,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )


def test_hourly_schedule_overlaps_during_repeated_active_window() -> None:
    result = recurring_schedule_overlaps(
        schedule=BASE_HOURLY_SCHEDULE,
        planned_start_time=datetime(
            2026, 8, 18, 16, 10,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 18, 16, 20,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    assert result is True


def test_hourly_schedule_does_not_overlap_between_active_windows() -> None:
    result = recurring_schedule_overlaps(
        schedule=BASE_HOURLY_SCHEDULE,
        planned_start_time=datetime(
            2026, 8, 18, 16, 35,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 18, 16, 50,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    assert result is False


def test_hourly_schedule_respects_every_hours_interval() -> None:
    schedule = replace(
        BASE_HOURLY_SCHEDULE,
        recurrence_pattern=HourlyRepetition(every_hours=2),
    )

    inactive_result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 18, 16, 10,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 18, 16, 20,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )
    active_result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 18, 17, 10,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 18, 17, 20,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    assert inactive_result is False
    assert active_result is True


def test_hourly_schedule_continues_repeating_after_midnight() -> None:
    result = recurring_schedule_overlaps(
        schedule=BASE_HOURLY_SCHEDULE,
        planned_start_time=datetime(
            2026, 8, 19, 0, 10,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 19, 0, 20,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    assert result is True


def test_hourly_schedule_does_not_activate_on_excluded_date() -> None:
    schedule = replace(
        BASE_HOURLY_SCHEDULE,
        excluded_dates=(date(2026, 8, 19),),
    )

    result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 19, 16, 10,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 19, 16, 20,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    assert result is False


def test_hourly_schedule_does_not_activate_after_effective_until() -> None:
    result = recurring_schedule_overlaps(
        schedule=BASE_HOURLY_SCHEDULE,
        planned_start_time=datetime(
            2026, 8, 20, 16, 10,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 20, 16, 20,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    assert result is False


@pytest.mark.parametrize("every_hours", [0, -1])
def test_hourly_schedule_rejects_invalid_interval(every_hours: int) -> None:
    schedule = replace(
        BASE_HOURLY_SCHEDULE,
        recurrence_pattern=HourlyRepetition(every_hours=every_hours),
    )

    with pytest.raises(
        ValueError,
        match="every_hours must be at least 1",
    ):
        recurring_schedule_overlaps(
            schedule=schedule,
            planned_start_time=datetime(
                2026, 8, 18, 16, 10,
                tzinfo=SINGAPORE_TIMEZONE,
            ),
            planned_end_time=datetime(
                2026, 8, 18, 16, 20,
                tzinfo=SINGAPORE_TIMEZONE,
            ),
        )

def test_daily_schedule_overlaps_flight_during_active_hours() -> None:
    singapore_timezone = ZoneInfo("Asia/Singapore")
    schedule = RecurringSchedule(
        timezone="Asia/Singapore",
        effective_from=datetime(
            2026, 8, 1, 15, 0,
            tzinfo=singapore_timezone,
        ),
        duration=timedelta(hours=3),
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
        effective_from=datetime(
            2026, 8, 1, 15, 0,
            tzinfo=singapore_timezone,
        ),
        duration=timedelta(hours=3),
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
        effective_from=datetime(
            2026, 8, 1, 15, 0,
            tzinfo=singapore_timezone,
        ),
        duration=timedelta(hours=3),
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
        effective_from=datetime(
            2026, 8, 1, 15, 0,
            tzinfo=singapore_timezone,
        ),
        duration=timedelta(hours=3),
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
        effective_from=datetime(
            2026, 8, 1, 15, 0,
            tzinfo=singapore_timezone,
        ),
        duration=timedelta(hours=3),
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
        effective_from=datetime(
            2026, 8, 10, 15, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        effective_until=singapore_end_of_day(2026, 8, 20),
    )
    assert overlaps_on_august_day(schedule, 9) is False
    assert overlaps_on_august_day(schedule, 10) is True
    assert overlaps_on_august_day(schedule, 20) is True
    assert overlaps_on_august_day(schedule, 21) is False


def test_daily_schedule_detects_occurrence_that_continues_past_midnight() -> None:
    schedule = replace(
        BASE_DAILY_SCHEDULE,
        effective_from=datetime(
            2026, 8, 15, 22, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        duration=timedelta(hours=4),
    )

    result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 16, 1, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 16, 1, 30,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    assert result is True


def test_exact_effective_until_shortens_final_occurrence() -> None:
    schedule = replace(
        BASE_DAILY_SCHEDULE,
        effective_until=datetime(
            2026, 8, 15, 16, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    before_cutoff = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 15, 15, 30,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 15, 15, 45,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )
    after_cutoff = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 15, 16, 30,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 15, 17, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    assert before_cutoff is True
    assert after_cutoff is False
    
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

def test_daily_schedule_rejects_non_positive_duration() -> None:
    schedule = replace(
        BASE_DAILY_SCHEDULE,
        duration=timedelta(0),
    )
    with pytest.raises(ValueError, match="duration"):
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
        effective_from=datetime(
            2026, 8, 20, 15, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        effective_until=singapore_end_of_day(2026, 8, 10),
    )
    with pytest.raises(ValueError, match="effective_until"):
        overlaps_on_august_day(schedule, 15)


@pytest.mark.parametrize("selected_day", (3, 5, 7))
def test_weekly_schedule_overlaps_on_each_selected_weekday(
    selected_day: int,
) -> None:
    assert overlaps_on_august_day(
        BASE_WEEKLY_SCHEDULE,
        selected_day,
    ) is True

def test_weekly_schedule_does_not_overlap_on_unselected_weekday() -> None:
    assert overlaps_on_august_day(
        BASE_WEEKLY_SCHEDULE,
        day=4,
    ) is False

def test_weekly_schedule_respects_every_weeks_interval() -> None:
    schedule = replace(
        BASE_WEEKLY_SCHEDULE,
        recurrence_pattern=WeeklyRepetition(
            days_of_week=(Weekday.MONDAY,),
            every_weeks=2,
        ),
    )
    assert overlaps_on_august_day(schedule, day=3) is True
    assert overlaps_on_august_day(schedule, day=10) is False
    assert overlaps_on_august_day(schedule, day=17) is True

def test_weekly_schedule_checks_next_day_when_flight_crosses_midnight() -> None:
    result = recurring_schedule_overlaps(
        schedule=BASE_WEEKLY_SCHEDULE,
        planned_start_time=datetime(
            2026, 8, 9, 19, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 8, 10, 16, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )
    assert result is True

def test_weekly_schedule_does_not_activate_on_excluded_date() -> None:
    schedule = replace(
        BASE_WEEKLY_SCHEDULE,
        excluded_dates=(date(2026, 8, 5),),
    )
    assert overlaps_on_august_day(schedule, day=5) is False

def test_weekly_schedule_respects_effective_until_date() -> None:
    schedule = replace(
        BASE_WEEKLY_SCHEDULE,
        effective_until=singapore_end_of_day(2026, 8, 5),
    )
    assert overlaps_on_august_day(schedule, day=5) is True
    assert overlaps_on_august_day(schedule, day=7) is False

def test_weekly_schedule_uses_weekday_in_schedule_timezone() -> None:
    utc_timezone = ZoneInfo("UTC")
    schedule = replace(
        BASE_WEEKLY_SCHEDULE,
        effective_from=datetime(
            2026, 8, 3, 1, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        duration=timedelta(hours=2),
        recurrence_pattern=WeeklyRepetition(
            days_of_week=(Weekday.MONDAY,),
        ),
    )
    result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 2, 17, 30,
            tzinfo=utc_timezone,
        ),
        planned_end_time=datetime(
            2026, 8, 2, 18, 30,
            tzinfo=utc_timezone,
        ),
    )
    assert result is True

@pytest.mark.parametrize("every_weeks", (0, -1))
def test_weekly_schedule_rejects_non_positive_interval(
    every_weeks: int,
) -> None:
    schedule = replace(
        BASE_WEEKLY_SCHEDULE,
        recurrence_pattern=WeeklyRepetition(
            days_of_week=(Weekday.MONDAY,),
            every_weeks=every_weeks,
        ),
    )
    with pytest.raises(ValueError, match="every_weeks"):
        overlaps_on_august_day(schedule, day=3)

def test_weekly_schedule_rejects_empty_weekday_selection() -> None:
    schedule = replace(
        BASE_WEEKLY_SCHEDULE,
        recurrence_pattern=WeeklyRepetition(
            days_of_week=(),
        ),
    )
    with pytest.raises(ValueError, match="days_of_week"):
        overlaps_on_august_day(schedule, day=3)


@pytest.mark.parametrize("selected_day", (18, 21, 23))
def test_monthly_specific_days_overlap_on_each_selected_date(
    selected_day: int,
) -> None:
    assert overlaps_on_august_day(
        BASE_MONTHLY_SCHEDULE,
        selected_day,
    ) is True

def test_monthly_specific_days_do_not_overlap_on_unselected_date() -> None:
    assert overlaps_on_august_day(
        BASE_MONTHLY_SCHEDULE,
        day=22,
    ) is False

def test_monthly_schedule_respects_every_months_interval() -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=SpecificDaysOfMonth(days=(15,)),
            every_months=2,
        ),
    )
    assert overlaps_on_date(schedule, date(2026, 1, 15)) is True
    assert overlaps_on_date(schedule, date(2026, 2, 15)) is False
    assert overlaps_on_date(schedule, date(2026, 3, 15)) is True

def test_monthly_specific_day_is_skipped_when_month_is_too_short() -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=SpecificDaysOfMonth(days=(31,)),
        ),
    )
    assert overlaps_on_date(schedule, date(2026, 6, 30)) is False
    assert overlaps_on_date(schedule, date(2026, 7, 31)) is True


def test_monthly_february_29_only_occurs_in_leap_year() -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=SpecificDaysOfMonth(days=(29,)),
        ),
    )

    assert overlaps_on_date(schedule, date(2026, 2, 28)) is False
    assert overlaps_on_date(schedule, date(2028, 2, 29)) is True

@pytest.mark.parametrize(
    ("position", "expected_day"),
    (
        (WeekPosition.FIRST, 2),
        (WeekPosition.SECOND, 9),
        (WeekPosition.THIRD, 16),
        (WeekPosition.FOURTH, 23),
        (WeekPosition.FIFTH, 30),
        (WeekPosition.LAST, 30),
    ),
)
def test_monthly_nth_weekday_overlaps_selected_occurrence(
    position: WeekPosition,
    expected_day: int,
) -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=NthWeekdayOfMonth(
                position=position,
                weekday=Weekday.SUNDAY,
            ),
        ),
    )

    assert overlaps_on_august_day(schedule, expected_day) is True

def test_monthly_nth_weekday_does_not_overlap_wrong_occurrence() -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=NthWeekdayOfMonth(
                position=WeekPosition.FOURTH,
                weekday=Weekday.SUNDAY,
            ),
        ),
    )
    assert overlaps_on_august_day(schedule, day=16) is False

def test_monthly_fifth_weekday_is_inactive_when_it_does_not_exist() -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=NthWeekdayOfMonth(
                position=WeekPosition.FIFTH,
                weekday=Weekday.SUNDAY,
            ),
        ),
    )
    assert overlaps_on_date(schedule, date(2026, 9, 27)) is False

def test_monthly_schedule_checks_next_month_when_flight_crosses_midnight() -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=SpecificDaysOfMonth(days=(1,)),
        ),
    )

    result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 8, 31, 19, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2026, 9, 1, 16, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )

    assert result is True

@pytest.mark.parametrize("every_months", (0, -1))
def test_monthly_schedule_rejects_non_positive_interval(
    every_months: int,
) -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=SpecificDaysOfMonth(days=(15,)),
            every_months=every_months,
        ),
    )

    with pytest.raises(ValueError, match="every_months"):
        overlaps_on_date(schedule, date(2026, 1, 15))

def test_monthly_schedule_rejects_empty_specific_day_selection() -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=SpecificDaysOfMonth(days=()),
        ),
    )

    with pytest.raises(ValueError, match="days"):
        overlaps_on_date(schedule, date(2026, 1, 15))

@pytest.mark.parametrize("invalid_day", (0, 32))
def test_monthly_schedule_rejects_invalid_specific_day(
    invalid_day: int,
) -> None:
    schedule = replace(
        BASE_MONTHLY_SCHEDULE,
        recurrence_pattern=MonthlyRepetition(
            date_selection=SpecificDaysOfMonth(
                days=(invalid_day,),
            ),
        ),
    )
    with pytest.raises(ValueError, match="days"):
        overlaps_on_date(schedule, date(2026, 1, 15))


@pytest.mark.parametrize(
    "selected_date",
    (
        date(2026, 8, 18),
        date(2026, 10, 21),
    ),
)
def test_yearly_specific_days_overlap_in_each_selected_month(
    selected_date: date,
) -> None:
    assert overlaps_on_date(
        BASE_YEARLY_SCHEDULE,
        selected_date,
    ) is True

def test_yearly_specific_days_do_not_overlap_on_unselected_date() -> None:
    assert overlaps_on_date(
        BASE_YEARLY_SCHEDULE,
        date(2026, 8, 20),
    ) is False

def test_yearly_schedule_does_not_overlap_in_unselected_month() -> None:
    assert overlaps_on_date(
        BASE_YEARLY_SCHEDULE,
        date(2026, 9, 18),
    ) is False

def test_yearly_schedule_respects_every_years_interval() -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.AUGUST,),
            date_selection=SpecificDaysOfMonth(days=(15,)),
            every_years=2,
        ),
    )
    assert overlaps_on_date(schedule, date(2026, 8, 15)) is True
    assert overlaps_on_date(schedule, date(2027, 8, 15)) is False
    assert overlaps_on_date(schedule, date(2028, 8, 15)) is True

def test_yearly_specific_day_is_skipped_when_month_is_too_short() -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.JUNE, Month.JULY),
            date_selection=SpecificDaysOfMonth(days=(31,)),
        ),
    )
    assert overlaps_on_date(schedule, date(2026, 6, 30)) is False
    assert overlaps_on_date(schedule, date(2026, 7, 31)) is True

def test_yearly_february_29_only_occurs_in_leap_year() -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.FEBRUARY,),
            date_selection=SpecificDaysOfMonth(days=(29,)),
        ),
    )
    assert overlaps_on_date(schedule, date(2026, 2, 28)) is False
    assert overlaps_on_date(schedule, date(2028, 2, 29)) is True

@pytest.mark.parametrize(
    "selected_date",
    (
        date(2026, 8, 23),
        date(2026, 10, 25),
    ),
)
def test_yearly_nth_weekday_overlaps_in_each_selected_month(
    selected_date: date,
) -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.AUGUST, Month.OCTOBER),
            date_selection=NthWeekdayOfMonth(
                position=WeekPosition.FOURTH,
                weekday=Weekday.SUNDAY,
            ),
        ),
    )
    assert overlaps_on_date(schedule, selected_date) is True

def test_yearly_nth_weekday_does_not_overlap_wrong_occurrence() -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.AUGUST,),
            date_selection=NthWeekdayOfMonth(
                position=WeekPosition.FOURTH,
                weekday=Weekday.SUNDAY,
            ),
        ),
    )
    assert overlaps_on_date(schedule, date(2026, 8, 16)) is False

def test_yearly_last_weekday_overlaps_selected_occurrence() -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.AUGUST,),
            date_selection=NthWeekdayOfMonth(
                position=WeekPosition.LAST,
                weekday=Weekday.SUNDAY,
            ),
        ),
    )
    assert overlaps_on_date(schedule, date(2026, 8, 30)) is True

def test_yearly_schedule_checks_next_year_when_flight_crosses_midnight() -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.JANUARY,),
            date_selection=SpecificDaysOfMonth(days=(1,)),
        ),
    )
    result = recurring_schedule_overlaps(
        schedule=schedule,
        planned_start_time=datetime(
            2026, 12, 31, 19, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
        planned_end_time=datetime(
            2027, 1, 1, 16, 0,
            tzinfo=SINGAPORE_TIMEZONE,
        ),
    )
    assert result is True

@pytest.mark.parametrize("every_years", (0, -1))
def test_yearly_schedule_rejects_non_positive_interval(
    every_years: int,
) -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.AUGUST,),
            date_selection=SpecificDaysOfMonth(days=(15,)),
            every_years=every_years,
        ),
    )
    with pytest.raises(ValueError, match="every_years"):
        overlaps_on_date(schedule, date(2026, 8, 15))

def test_yearly_schedule_rejects_empty_month_selection() -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(),
            date_selection=SpecificDaysOfMonth(days=(15,)),
        ),
    )
    with pytest.raises(ValueError, match="months"):
        overlaps_on_date(schedule, date(2026, 8, 15))

def test_yearly_schedule_rejects_empty_specific_day_selection() -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.AUGUST,),
            date_selection=SpecificDaysOfMonth(days=()),
        ),
    )
    with pytest.raises(ValueError, match="days"):
        overlaps_on_date(schedule, date(2026, 8, 15))

@pytest.mark.parametrize("invalid_day", (0, 32))
def test_yearly_schedule_rejects_invalid_specific_day(
    invalid_day: int,
) -> None:
    schedule = replace(
        BASE_YEARLY_SCHEDULE,
        recurrence_pattern=YearlyRepetition(
            months=(Month.AUGUST,),
            date_selection=SpecificDaysOfMonth(
                days=(invalid_day,),
            ),
        ),
    )
    with pytest.raises(ValueError, match="days"):
        overlaps_on_date(schedule, date(2026, 8, 15))
