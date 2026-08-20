from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from tools.route_airspace_compliance.checkers.nfz_checker import check_waypoint_against_nfzs
from tools.route_airspace_compliance.decision_types import CheckResult
from tools.route_airspace_compliance.recurrence_schemas import (
    DailyRepetition,
    HourlyRepetition,
    RecurringSchedule,
)
from tools.route_airspace_compliance.request_response_schemas import Waypoint
from tools.route_airspace_compliance.tests.fakes import FakeAirspaceClient
from tools.route_airspace_compliance.tests.fixtures.nfz_responses import ACTIVE_RESTRICTED_NFZ, HIGH_ALTITUDE_NFZ, INACTIVE_RESTRICTED_NFZ, PLANNED_START_TIME, PLANNED_END_TIME

SINGAPORE_TIMEZONE = ZoneInfo("Asia/Singapore")

def test_waypoint_is_clear_when_no_nfzs_are_found() -> None:
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20
    )
    client = FakeAirspaceClient()
    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client
    )
    assert result.result is CheckResult.CLEAR
    assert result.matched_nfzs == ()
    assert client.queries == [(103.8001, 1.3001)]
    
    
def test_active_nfzs_with_altitude_overlap_is_a_violation() -> None:
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20
    )
    client = FakeAirspaceClient(
        nfzs=[ACTIVE_RESTRICTED_NFZ],
    )
    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client
    )
    assert result.result is CheckResult.VIOLATION
    assert len(result.matched_nfzs) == 1
    
    match = result.matched_nfzs[0]
    assert match.nfz_id == "NFZ-001"
    assert match.altitude_conflict is True
    assert match.time_conflict is True
    
    
def test_inactive_nfz_does_not_violate_waypoint() -> None:
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20
    )
    client = FakeAirspaceClient(
        nfzs=[INACTIVE_RESTRICTED_NFZ]
    )
    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client
    )
    assert result.result is CheckResult.CLEAR
    assert result.matched_nfzs == ()
    
    
def test_nfz_above_waypoint_altitude_does_not_violate() -> None:
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20
    )
    client = FakeAirspaceClient(
        nfzs=[HIGH_ALTITUDE_NFZ],
    )
    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client
    )
    assert result.result is CheckResult.CLEAR
    assert result.matched_nfzs == ()
    

def test_unavailable_client_returns_unavailable_result() -> None:
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20
    )
    client = FakeAirspaceClient(unavailable=True)
    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client
    )
    assert result.result is CheckResult.UNAVAILABLE
    assert result.matched_nfzs == ()
    assert client.queries == [(103.8001, 1.3001)]
    

def test_incomplete_nfz_data_returns_unavailable() -> None:
    incomplete_nfz = replace(
        ACTIVE_RESTRICTED_NFZ,
        valid_until=None
    )
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20
    )
    client = FakeAirspaceClient(
        nfzs=[incomplete_nfz]
    )
    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client
    )
    assert result.result is CheckResult.UNAVAILABLE
    assert result.matched_nfzs == ()
    

def test_confirmed_violation_takes_priority_over_incomplete_data() -> None:
    incomplete_nfz = replace(
        ACTIVE_RESTRICTED_NFZ,
        nfz_id="NFZ-INCOMPLETE",
        valid_until=None,
    )
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20,
    )
    client = FakeAirspaceClient(
        nfzs=[incomplete_nfz, ACTIVE_RESTRICTED_NFZ],
    )
    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client,
    )
    assert result.result is CheckResult.VIOLATION
    assert len(result.matched_nfzs) == 1
    assert result.matched_nfzs[0].nfz_id == "NFZ-001"


def test_active_recurring_nfz_is_violation_without_absolute_dates() -> None:
    recurring_nfz = replace(
        ACTIVE_RESTRICTED_NFZ,
        nfz_id="NFZ-RECURRING-ACTIVE",
        valid_from=None,
        valid_until=None,
        recurring_schedule=RecurringSchedule(
            timezone="Asia/Singapore",
            effective_from=datetime(
                2026, 8, 1, 8, 0,
                tzinfo=SINGAPORE_TIMEZONE,
            ),
            duration=timedelta(hours=3),
            recurrence_pattern=DailyRepetition(),
        ),
    )
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20,
    )
    client = FakeAirspaceClient(nfzs=[recurring_nfz])

    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client,
    )

    assert result.result is CheckResult.VIOLATION
    assert result.matched_nfzs[0].nfz_id == "NFZ-RECURRING-ACTIVE"


def test_active_hourly_nfz_is_a_violation() -> None:
    recurring_nfz = replace(
        ACTIVE_RESTRICTED_NFZ,
        nfz_id="NFZ-HOURLY-ACTIVE",
        valid_from=None,
        valid_until=None,
        recurring_schedule=RecurringSchedule(
            timezone="Asia/Singapore",
            effective_from=datetime(
                2026, 8, 10, 8, 0,
                tzinfo=SINGAPORE_TIMEZONE,
            ),
            duration=timedelta(minutes=30),
            recurrence_pattern=HourlyRepetition(every_hours=1),
        ),
    )
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20,
    )
    client = FakeAirspaceClient(nfzs=[recurring_nfz])

    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client,
    )

    assert result.result is CheckResult.VIOLATION
    assert result.matched_nfzs[0].nfz_id == "NFZ-HOURLY-ACTIVE"


def test_recurring_schedule_overrides_absolute_time_window() -> None:
    recurring_nfz = replace(
        ACTIVE_RESTRICTED_NFZ,
        nfz_id="NFZ-RECURRING-INACTIVE",
        recurring_schedule=RecurringSchedule(
            timezone="Asia/Singapore",
            effective_from=datetime(
                2026, 8, 1, 15, 0,
                tzinfo=SINGAPORE_TIMEZONE,
            ),
            duration=timedelta(hours=3),
            recurrence_pattern=DailyRepetition(),
        ),
    )
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20,
    )
    client = FakeAirspaceClient(nfzs=[recurring_nfz])

    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client,
    )

    assert result.result is CheckResult.CLEAR
    assert result.matched_nfzs == ()


def test_invalid_recurring_schedule_returns_unavailable() -> None:
    recurring_nfz = replace(
        ACTIVE_RESTRICTED_NFZ,
        nfz_id="NFZ-RECURRING-INVALID",
        recurring_schedule=RecurringSchedule(
            timezone="Not/A-Real-Timezone",
            effective_from=datetime(
                2026, 8, 1, 8, 0,
                tzinfo=SINGAPORE_TIMEZONE,
            ),
            duration=timedelta(hours=3),
            recurrence_pattern=DailyRepetition(),
        ),
    )
    waypoint = Waypoint(
        sequence=1,
        longitude=103.8001,
        latitude=1.3001,
        altitude_m=20,
    )
    client = FakeAirspaceClient(nfzs=[recurring_nfz])

    result = check_waypoint_against_nfzs(
        waypoint=waypoint,
        planned_start_time=PLANNED_START_TIME,
        planned_end_time=PLANNED_END_TIME,
        client=client,
    )

    assert result.result is CheckResult.UNAVAILABLE
    assert result.matched_nfzs == ()
