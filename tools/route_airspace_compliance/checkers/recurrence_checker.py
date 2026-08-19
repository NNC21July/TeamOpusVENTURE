from calendar import monthrange
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from tools.route_airspace_compliance.recurrence_schemas import (
    DailyRepetition,
    MonthlyRepetition,
    NthWeekdayOfMonth,
    RecurringSchedule,
    SpecificDaysOfMonth,
    Weekday,
    WeeklyRepetition,
    WeekPosition
)

PYTHON_WEEKDAYS = (
    Weekday.MONDAY,
    Weekday.TUESDAY,
    Weekday.WEDNESDAY,
    Weekday.THURSDAY,
    Weekday.FRIDAY,
    Weekday.SATURDAY,
    Weekday.SUNDAY,
)

def recurring_schedule_overlaps(*, schedule: RecurringSchedule, planned_start_time: datetime, planned_end_time: datetime) -> bool:
    repetition = schedule.recurrence_pattern
    
    if isinstance(repetition, DailyRepetition):
        if repetition.every_days < 1:
            raise ValueError("every_days must be at least 1")
        
    elif isinstance(repetition, WeeklyRepetition):
        if repetition.every_weeks < 1:
            raise ValueError("every_weeks must be at least 1")
        if not repetition.days_of_week:
            raise ValueError("days_of_week must contain at least one weekday")
        
    elif isinstance(repetition, MonthlyRepetition):
        if repetition.every_months < 1:
            raise ValueError("every_months must be at least 1")
        selection = repetition.date_selection
        if isinstance(selection, SpecificDaysOfMonth):
            if not selection.days:
                raise ValueError("days must contain at least one date")
            if any(day < 1 or day > 31 for day in selection.days):
                raise ValueError(f"days must be between 1 and 31")
        elif not isinstance(selection, NthWeekdayOfMonth):
            raise ValueError("date_selection is unsupported")
        
    else:
        raise NotImplementedError("Only daily, weekly, and monthly repetition are implemented")
    
    
    if schedule.end_time <= schedule.start_time:
        raise ValueError("Overnight recurring schedules are not implemented")
    
    if schedule.effective_until is not None and schedule.effective_until < schedule.effective_from:
        raise ValueError("effective_until cannot be earlier than effective_from")

    if planned_start_time.tzinfo is None or planned_start_time.utcoffset() is None:
        raise ValueError("planned_start_time must be timezone-aware")
    if planned_end_time.tzinfo is None or planned_end_time.utcoffset() is None:
        raise ValueError("planned_end_time must be timezone-aware")
    if planned_end_time <= planned_start_time:
        raise ValueError("planned_end_time must be later than planned_start_time")
    
    try:
        schedule_timezone = ZoneInfo(schedule.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"timezone is unknown: {schedule.timezone}") from exc
    
    local_flight_start = planned_start_time.astimezone(schedule_timezone)
    local_flight_end = planned_end_time.astimezone(schedule_timezone)
    first_flight_date = local_flight_start.date()
    last_flight_date = local_flight_end.date()
    num_of_dates = (last_flight_date - first_flight_date).days + 1
    
    for day_offset in range(num_of_dates):
        scheduled_date = first_flight_date + timedelta(days=day_offset)
        
        if scheduled_date < schedule.effective_from:
            continue
        if schedule.effective_until is not None and scheduled_date > schedule.effective_until:
            continue
        if scheduled_date in schedule.excluded_dates:
            continue
        
        days_since_start = (scheduled_date - schedule.effective_from).days
        if isinstance(repetition, DailyRepetition):
            if days_since_start % repetition.every_days != 0:
                continue
        elif isinstance(repetition, WeeklyRepetition):
            scheduled_weekday = PYTHON_WEEKDAYS[scheduled_date.weekday()]
            if scheduled_weekday not in repetition.days_of_week:
                continue
            
            weeks_since_start = days_since_start // 7
            if weeks_since_start % repetition.every_weeks != 0:
                continue
        elif isinstance(repetition, MonthlyRepetition):
            months_since_start = ((scheduled_date.year - schedule.effective_from.year) * 12 + scheduled_date.month - schedule.effective_from.month)
            if months_since_start % repetition.every_months != 0:
                continue
            selection = repetition.date_selection
            days_in_month = monthrange(scheduled_date.year, scheduled_date.month)[1]
            if isinstance(selection, SpecificDaysOfMonth):
                valid_days = {day for day in selection.days if day <= days_in_month}
                if scheduled_date.day not in valid_days:
                    continue
            elif isinstance(selection, NthWeekdayOfMonth):
                scheduled_weekday = PYTHON_WEEKDAYS[scheduled_date.weekday()]
                if scheduled_weekday != selection.weekday:
                    continue
                if selection.position == WeekPosition.LAST:
                    if scheduled_date.day + 7 <= days_in_month:
                        continue
                else:
                    occurence_num = (scheduled_date.day - 1) // 7 + 1
                    if occurence_num != selection.position.value:
                        continue
    
        activation_start = datetime.combine(
            scheduled_date,
            schedule.start_time,
            tzinfo=schedule_timezone
        )
        activation_end = datetime.combine(
            scheduled_date,
            schedule.end_time,
            tzinfo=schedule_timezone
        )
        if local_flight_start <= activation_end and local_flight_end >= activation_start:
            return True
        
    return False