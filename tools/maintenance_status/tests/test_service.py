"""End-to-end tests for get_drone_maintenance_status.

Covers the nine scenarios from the Research 2 test table, plus the behaviour
that falls out of there being no maintenance endpoint in Plex.
"""

import json
from datetime import datetime, timezone

import pytest

from tools.maintenance_status.hours_calculator import (
    SOURCE_COMPUTED,
    SOURCE_PLEX_AGGREGATE,
    hours_from_aggregate,
)
from tools.maintenance_status.output_shaper import (
    shape_maintenance_status_response,
)
from tools.maintenance_status.request_response_schemas import (
    MaintenanceStatusRequest,
)
from tools.maintenance_status.service import get_drone_maintenance_status
from tools.maintenance_status.status_types import MaintenanceStatus
from tools.maintenance_status.tests.fakes import FakeMaintenanceClient
from tools.maintenance_status.tests.fixtures import flight_records as fr
from tools.maintenance_status.tests.fixtures import maintenance_records as mr

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)


def run(
    *,
    drone="DRONE-001",
    client=None,
    flights=None,
    service_records=None,
    drone_ref=None,
):
    client = client or FakeMaintenanceClient(
        drone_ref or mr.KNOWN_DRONE,
        flights if flights is not None else fr.FRESHLY_SERVICED,
        service_records if service_records is not None else mr.NO_SERVICE_RECORDS,
    )
    return get_drone_maintenance_status(
        request=MaintenanceStatusRequest(drone=drone), client=client, now=NOW
    )


# --- the nine scenarios -----------------------------------------------------


def test_recently_serviced_low_hours_is_ok() -> None:
    response = run()
    assert response.status is MaintenanceStatus.OK
    assert response.hours_since_service == pytest.approx(42.0)
    assert response.service_interval_hours == 200.0


def test_hours_inside_the_warning_band_is_due_soon() -> None:
    response = run(flights=fr.NEAR_SERVICE_INTERVAL)
    assert response.status is MaintenanceStatus.DUE_SOON
    assert response.next_due_hours < 20.0


def test_hours_past_the_interval_is_overdue() -> None:
    response = run(flights=fr.PAST_SERVICE_INTERVAL)
    assert response.status is MaintenanceStatus.OVERDUE


def test_calendar_date_passed_is_overdue_with_low_hours() -> None:
    response = run(
        flights=fr.FRESHLY_SERVICED, service_records=mr.SERVICED_LONG_AGO
    )
    assert response.status is MaintenanceStatus.OVERDUE
    assert response.last_service_date is not None


def test_no_service_plan_on_record_is_needs_info() -> None:
    response = run(drone_ref=mr.UNKNOWN_MODEL_DRONE)
    assert response.status is MaintenanceStatus.NEEDS_INFO
    assert response.service_interval_hours is None


def test_unresolvable_drone_is_needs_info() -> None:
    response = run(client=FakeMaintenanceClient(not_found=True))
    assert response.status is MaintenanceStatus.NEEDS_INFO
    assert response.missing_inputs


def test_fleet_service_unavailable_is_unknown() -> None:
    response = run(client=FakeMaintenanceClient(fleet_unavailable=True))
    assert response.status is MaintenanceStatus.UNKNOWN


def test_hours_source_records_the_computed_path() -> None:
    assert run().hours_source == SOURCE_COMPUTED


def test_hours_source_distinguishes_an_aggregate() -> None:
    # No Plex aggregate exists yet, but the label must differ when one does.
    assert hours_from_aggregate(182.4).source == SOURCE_PLEX_AGGREGATE


# --- consequences of there being no maintenance endpoint --------------------


def test_missing_endpoint_is_recorded_as_an_assumption() -> None:
    response = run()
    assert any("no maintenance endpoint" in a.lower() for a in response.assumptions)
    assert any("calendar" in a.lower() for a in response.assumptions)


def test_local_service_plan_is_flagged() -> None:
    assert any("local service plan" in a.lower() for a in run().assumptions)


def test_no_service_record_means_no_calendar_dates() -> None:
    response = run()
    assert response.last_service_date is None
    assert response.next_due_date is None
    # But the hours verdict still stands.
    assert response.status is MaintenanceStatus.OK


def test_service_records_unavailable_is_unknown_not_needs_info() -> None:
    # "The service could not answer" differs from "this frame has no history".
    client = FakeMaintenanceClient(
        mr.KNOWN_DRONE, fr.FRESHLY_SERVICED, service_records_unavailable=True
    )
    assert run(client=client).status is MaintenanceStatus.UNKNOWN


def test_flight_records_unavailable_is_unknown() -> None:
    client = FakeMaintenanceClient(
        mr.KNOWN_DRONE, fr.FRESHLY_SERVICED, flights_unavailable=True
    )
    assert run(client=client).status is MaintenanceStatus.UNKNOWN


def test_latest_service_record_wins() -> None:
    response = run(service_records=mr.MULTIPLE_SERVICES)
    assert response.last_service_date is not None
    assert response.last_service_date.year == 2026
    assert response.last_service_date.month == 7
    assert response.last_service_type == "major"


def test_skipped_flights_are_reported_as_an_assumption() -> None:
    response = run(flights=fr.MISSING_DURATION)
    assert any("no usable duration" in a for a in response.assumptions)


def test_drone_with_no_model_cannot_be_planned() -> None:
    response = run(drone_ref=mr.NO_MODEL_DRONE)
    assert response.status is MaintenanceStatus.NEEDS_INFO


# --- input validation -------------------------------------------------------


def test_blank_drone_identifier_is_needs_info() -> None:
    response = run(drone="   ")
    assert response.status is MaintenanceStatus.NEEDS_INFO


def test_no_fleet_call_when_input_is_invalid() -> None:
    client = FakeMaintenanceClient(mr.KNOWN_DRONE, fr.FRESHLY_SERVICED)
    run(drone="", client=client)
    assert client.drone_queries == []


# --- output shaping ---------------------------------------------------------


def test_shaped_output_is_json_safe() -> None:
    shaped = shape_maintenance_status_response(run())
    json.dumps(shaped)
    assert shaped["status"] == "OK"
    assert shaped["hours_source"] == SOURCE_COMPUTED
    assert isinstance(shaped["data_checked_at"], str)


def test_hours_source_is_always_present_even_when_null() -> None:
    # It is the audit trail for the number, so a null is itself informative.
    shaped = shape_maintenance_status_response(run(drone="  "))
    assert "hours_source" in shaped
    assert shaped["hours_source"] is None


def test_shaped_output_drops_absent_dates() -> None:
    shaped = shape_maintenance_status_response(run())
    assert "last_service_date" not in shaped
    assert "next_due_date" not in shaped
