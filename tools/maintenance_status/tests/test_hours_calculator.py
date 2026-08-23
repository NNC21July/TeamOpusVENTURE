from datetime import date, datetime, timezone

import pytest

from tools.maintenance_status.hours_calculator import (
    SOURCE_COMPUTED,
    SOURCE_PLEX_AGGREGATE,
    duration_seconds_from_parts,
    epoch_ms_to_datetime,
    hours_from_aggregate,
    sum_flight_hours,
)
from tools.maintenance_status.request_response_schemas import FlightRecord
from tools.maintenance_status.tests.fixtures import flight_records as fr


def test_sums_a_weekly_tempo() -> None:
    result = sum_flight_hours(fr.FRESHLY_SERVICED)
    assert result.hours == pytest.approx(42.0)
    assert result.flights_counted == 63
    assert result.source == SOURCE_COMPUTED


def test_near_interval_fixture_lands_in_the_warning_band() -> None:
    # 274 sorties x 40 min = 182.67 h, inside 10% of a 200 h interval.
    assert sum_flight_hours(fr.NEAR_SERVICE_INTERVAL).hours == pytest.approx(182.67)


def test_past_interval_fixture_exceeds_the_interval() -> None:
    assert sum_flight_hours(fr.PAST_SERVICE_INTERVAL).hours > 200.0


def test_no_flights_is_zero_hours_not_unknown() -> None:
    result = sum_flight_hours(fr.NO_FLIGHTS)
    assert result.hours == 0.0
    assert result.flights_counted == 0


def test_missing_duration_is_skipped_and_reported() -> None:
    # Counting a missing duration as zero would understate airframe hours,
    # which is the direction that hides an overdue airframe.
    result = sum_flight_hours(fr.MISSING_DURATION)
    assert result.flights_counted == 1
    assert result.flights_skipped == 1
    assert result.hours == pytest.approx(0.67, abs=0.01)


def test_negative_duration_is_skipped() -> None:
    records = [FlightRecord(flight_id="x", duration_seconds=-3600)]
    assert sum_flight_hours(records).flights_skipped == 1


def test_dateless_flight_counts_when_no_service_date_given() -> None:
    assert sum_flight_hours(fr.MISSING_DATE).flights_counted == 1


def test_dateless_flight_is_skipped_once_a_service_date_exists() -> None:
    # It cannot be placed relative to the service, so it is excluded and the
    # exclusion is reported rather than silently assumed either way.
    result = sum_flight_hours(fr.MISSING_DATE, since=date(2026, 1, 1))
    assert result.flights_counted == 0
    assert result.flights_skipped == 1


def test_only_flights_after_the_service_are_counted() -> None:
    all_flights = sum_flight_hours(fr.FRESHLY_SERVICED)
    since_recent = sum_flight_hours(fr.FRESHLY_SERVICED, since=date(2026, 8, 1))
    assert since_recent.hours < all_flights.hours
    assert since_recent.flights_counted < all_flights.flights_counted


def test_service_date_in_the_future_counts_nothing() -> None:
    assert sum_flight_hours(fr.FRESHLY_SERVICED, since=date(2027, 1, 1)).hours == 0.0


def test_aggregate_path_is_labelled_differently() -> None:
    result = hours_from_aggregate(182.4)
    assert result.hours == pytest.approx(182.4)
    assert result.source == SOURCE_PLEX_AGGREGATE
    assert result.source != SOURCE_COMPUTED


# --- Plex payload conversion ------------------------------------------------


def test_duration_object_is_flattened_to_seconds() -> None:
    assert duration_seconds_from_parts(
        {"hours": 1, "minutes": 30, "seconds": 15}
    ) == pytest.approx(5415.0)


def test_partial_duration_object_is_accepted() -> None:
    assert duration_seconds_from_parts({"minutes": 40}) == pytest.approx(2400.0)


def test_non_dict_duration_is_none_not_zero() -> None:
    assert duration_seconds_from_parts(None) is None
    assert duration_seconds_from_parts(3600) is None


def test_epoch_milliseconds_become_aware_datetimes() -> None:
    parsed = epoch_ms_to_datetime(1_787_000_000_000)
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo is not None


def test_unset_date_sentinel_is_none() -> None:
    # Plex reports -1 when a flight has no date set.
    assert epoch_ms_to_datetime(-1) is None
    assert epoch_ms_to_datetime(0) is None
    assert epoch_ms_to_datetime(None) is None
    assert epoch_ms_to_datetime(True) is None


def test_naive_flight_dates_are_handled() -> None:
    records = [
        FlightRecord(
            flight_id="x",
            flown_on=datetime(2026, 8, 20, 9, 0),
            duration_seconds=3600,
        )
    ]
    assert sum_flight_hours(records, since=date(2026, 8, 1)).flights_counted == 1
    assert (
        sum_flight_hours(records, since=date(2026, 8, 1))
        .hours
        == pytest.approx(1.0)
    )
    assert datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc).date() == date(2026, 8, 20)
