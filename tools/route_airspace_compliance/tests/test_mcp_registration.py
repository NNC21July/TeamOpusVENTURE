import asyncio
from datetime import datetime, timezone

import pytest

import server
from tools.route_airspace_compliance.request_response_schemas import (
    RouteComplianceRequest,
    Waypoint,
)


if not hasattr(server, "check_route_airspace_compliance"):
    pytest.skip(
        "waiting for route compliance MCP registration",
        allow_module_level=True,
    )


class EmptyAirspaceClient:
    def __init__(self) -> None:
        self.queries: list[tuple[float, float]] = []

    def query_nfzs(self, *, longitude: float, latitude: float) -> list:
        self.queries.append((longitude, latitude))
        return []


def test_route_compliance_mcp_tool_uses_client_and_returns_plain_data(
    monkeypatch,
) -> None:
    fake_client = EmptyAirspaceClient()
    monkeypatch.setattr(server, "GarudaAirspaceClient", lambda: fake_client)

    request = RouteComplianceRequest(
        waypoints=[
            Waypoint(
                sequence=1,
                longitude=103.8,
                latitude=1.3,
                altitude_m=30,
            )
        ],
        planned_start_time=datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
        planned_end_time=datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc),
    )

    result = server.check_route_airspace_compliance(request=request)

    assert fake_client.queries == [(103.8, 1.3)]
    assert result["decision"] == "PASS"
    assert result["route_clear"] is True
    assert result["waypoint_results"][0]["result"] == "CLEAR"
    assert isinstance(result["data_checked_at"], str)


def test_route_compliance_function_is_registered_as_an_mcp_tool() -> None:
    registered_tools = asyncio.run(server.mcp.list_tools())
    registered_names = {tool.name for tool in registered_tools}

    assert "check_route_airspace_compliance" in registered_names
