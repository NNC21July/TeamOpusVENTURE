from dataclasses import dataclass
from datetime import datetime, date, datetime, timedelta
from enum import Enum, IntEnum


class Weekday(str, Enum):
    MONDAY = "MON"
    TUESDAY = "TUE"
    WEDNESDAY = "WED"
    THURSDAY = "THU"
    FRIDAY = "FRI"
    SATURDAY = "SAT"
    SUNDAY = "SUN"


class Month(IntEnum):
    JANUARY = 1
    FEBRUARY = 2
    MARCH = 3
    APRIL = 4
    MAY = 5
    JUNE = 6
    JULY = 7
    AUGUST = 8
    SEPTEMBER = 9
    OCTOBER = 10
    NOVEMBER = 11
    DECEMBER = 12


class WeekPosition(IntEnum):
    FIRST = 1
    SECOND = 2
    THIRD = 3
    FOURTH = 4
    FIFTH = 5
    LAST = -1


@dataclass(frozen=True)
class SpecificDaysOfMonth:
    days: tuple[int, ...]


@dataclass(frozen=True)
class NthWeekdayOfMonth:
    position: WeekPosition
    weekday: Weekday


MonthDateSelection = (SpecificDaysOfMonth | NthWeekdayOfMonth)


@dataclass(frozen=True)
class HourlyRepetition:
    every_hours: int = 1


@dataclass(frozen=True)
class DailyRepetition:
    every_days: int = 1


@dataclass(frozen=True)
class WeeklyRepetition:
    days_of_week: tuple[Weekday, ...]
    every_weeks: int = 1


@dataclass(frozen=True)
class MonthlyRepetition:
    date_selection: MonthDateSelection
    every_months: int = 1


@dataclass(frozen=True)
class YearlyRepetition:
    months: tuple[Month, ...]
    date_selection: MonthDateSelection
    every_years: int = 1


RecurrencePattern = (
    HourlyRepetition | DailyRepetition | WeeklyRepetition | MonthlyRepetition | YearlyRepetition
)


@dataclass(frozen=True)
class RecurringSchedule:
    timezone: str
    effective_from: datetime
    duration: timedelta
    recurrence_pattern: RecurrencePattern
    effective_until: datetime | None = None
    excluded_dates: tuple[date, ...] = ()
