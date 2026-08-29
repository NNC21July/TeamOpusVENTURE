"""MCP registration tests for get_drone_maintenance_status.

Same skip-guard pattern as the other tools, so the file stays harmless if the
registration is ever removed.
"""

import asyncio

import pytest

import server

if not hasattr(server, "get_drone_maintenance_status"):
    pytest.skip(
        "waiting for maintenance status MCP registration",
        allow_module_level=True,
    )

from tools.maintenance_status.tests.fakes import FakeMaintenanceClient  # noqa: E402
from tools.maintenance_status.tests.fixtures import (  # noqa: E402
    flight_records as fr,
)
from tools.maintenance_status.tests.fixtures import (  # noqa: E402
    maintenance_records as mr,
)


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeMaintenanceClient(
        mr.KNOWN_DRONE, fr.FRESHLY_SERVICED, mr.NO_SERVICE_RECORDS
    )
    monkeypatch.setattr(server, "GarudaMaintenanceClient", lambda: client)
    return client


def test_returns_plain_json_safe_data(fake_client) -> None:
    import json

    result = server.get_drone_maintenance_status(drone="Falcon 1")

    json.dumps(result)
    assert result["status"] == "OK"
    assert result["hours_source"] == "computed_from_flight_records"
    assert isinstance(result["data_checked_at"], str)


def test_takes_a_bare_drone_string(fake_client) -> None:
    # A single string argument rather than a nested request object: the model
    # only has to say which drone, so the schema stays trivial to fill.
    server.get_drone_maintenance_status(drone="Falcon 1")
    assert fake_client.drone_queries == ["Falcon 1"]


def test_overdue_airframe_surfaces_through_the_tool(monkeypatch) -> None:
    client = FakeMaintenanceClient(
        mr.KNOWN_DRONE, fr.PAST_SERVICE_INTERVAL, mr.NO_SERVICE_RECORDS
    )
    monkeypatch.setattr(server, "GarudaMaintenanceClient", lambda: client)

    result = server.get_drone_maintenance_status(drone="Falcon 1")
    assert result["status"] == "OVERDUE"
    assert result["assumptions"]


def test_is_registered_as_an_mcp_tool() -> None:
    registered = asyncio.run(server.mcp.list_tools())
    assert "get_drone_maintenance_status" in {tool.name for tool in registered}


def test_is_not_governance_gated() -> None:
    # Read-only tools take no approval_request_id. If one appears here,
    # someone has wrapped a read-only lookup in the approval flow.
    import inspect

    signature = inspect.signature(server.get_drone_maintenance_status)
    assert "approval_request_id" not in signature.parameters


def test_description_names_the_question_it_answers() -> None:
    # The description is what the model selects on, so it is a deliverable.
    doc = server.get_drone_maintenance_status.__doc__ or ""
    assert "due for maintenance" in doc.lower()
    assert "read-only" in doc.lower()
