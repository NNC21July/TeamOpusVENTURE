"""MCP registration tests for check_flight_readiness.

Follows the skip-guard pattern already used by the route compliance tool, so
this file is harmless before the tool is wired into server.py and becomes a
real test the moment it is.

Registration itself is one function in server.py:

    @mcp.tool()
    def check_flight_readiness(request: FlightReadinessRequest) -> dict: ...

with NO @governed decorator and no governance/policy.py entry — the tool is
read-only, and that is how every read-only tool on the server is registered.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import server

if not hasattr(server, "check_flight_readiness"):
    pytest.skip(
        "waiting for flight readiness MCP registration",
        allow_module_level=True,
    )

from tools.flight_readiness.request_response_schemas import (  # noqa: E402
    FlightReadinessRequest,
    Location,
)
from tools.flight_readiness.tests.fakes import (  # noqa: E402
    FakeAircraftClient,
    FakeMaintenanceReader,
    FakeWeatherSource,
)
from tools.flight_readiness.tests.fixtures import aircraft_responses as ac  # noqa: E402
from tools.flight_readiness.tests.fixtures import battery_states as bat  # noqa: E402
from tools.flight_readiness.tests.fixtures import maintenance_records as mnt  # noqa: E402
from tools.flight_readiness.tests.fixtures import weather_responses as wx  # noqa: E402


def make_request() -> FlightReadinessRequest:
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    return FlightReadinessRequest(
        drone="DRONE-001",
        planned_start_time=start,
        planned_end_time=start + timedelta(hours=1),
        location=Location(longitude=103.8010, latitude=1.3010),
        planned_altitude_m=60.0,
        mission_duration_min=25.0,
    )


def test_flight_readiness_returns_plain_json_safe_data(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "GarudaAircraftClient",
        lambda **kwargs: FakeAircraftClient(ac.READY, bat.HEALTHY),
    )
    monkeypatch.setattr(
        server, "OpenMeteoClient", lambda **kwargs: FakeWeatherSource(wx.CALM)
    )
    monkeypatch.setattr(
        server, "NeaClient", lambda **kwargs: FakeWeatherSource(wx.CALM)
    )
    monkeypatch.setattr(
        server,
        "MaintenanceStatusReader",
        lambda **kwargs: FakeMaintenanceReader(mnt.FRESHLY_SERVICED),
        raising=False,
    )

    result = server.check_flight_readiness(request=make_request())

    assert result["decision"] in {
        "GO",
        "GO_WITH_WARNINGS",
        "NO_GO",
        "NEEDS_INFO",
        "UNKNOWN",
    }
    assert isinstance(result["data_checked_at"], str)

    import json

    json.dumps(result)


def test_flight_readiness_is_registered_as_an_mcp_tool() -> None:
    registered = asyncio.run(server.mcp.list_tools())
    assert "check_flight_readiness" in {tool.name for tool in registered}


def test_flight_readiness_is_not_governance_gated() -> None:
    # Read-only tools are registered with @mcp.tool() alone. If this tool ever
    # acquires an approval_request_id parameter, someone has wrapped a
    # read-only assessment in the approval flow by mistake.
    import inspect

    signature = inspect.signature(server.check_flight_readiness)
    assert "approval_request_id" not in signature.parameters
