"""Drive the MCP server over stdio, exactly as Claude Desktop does.

Every other registration test calls the tool function in-process. This one
spawns `python server.py` as a subprocess, performs the real MCP handshake
over stdin/stdout, and calls tools through the protocol — so it catches a
class of failure the in-process tests cannot:

  * a stray print() anywhere on the import path corrupts the JSON-RPC framing
    and silently breaks the Claude Desktop connection
  * a tool whose return value is not JSON-serialisable fails only at the
    transport boundary
  * an import error in server.py shows up as a dead server rather than a
    collection error

Runs in demo mode so it needs no credentials and no network.

Slower than the rest of the suite because it starts a subprocess. Deselect
with `-m "not stdio"` if that matters.
"""

import asyncio
import json
import os
import sys

import pytest

pytestmark = pytest.mark.stdio

mcp_client = pytest.importorskip("mcp.client.stdio")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


async def _drive(tool_name: str | None = None, arguments: dict | None = None):
    params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(REPO_ROOT, "server.py")],
        cwd=REPO_ROOT,
        env={**os.environ, "GARUDA_DEMO_MODE": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            if tool_name is None:
                return listing, None
            result = await session.call_tool(tool_name, arguments or {})
            return listing, result


def run(tool_name=None, arguments=None):
    return asyncio.run(_drive(tool_name, arguments))


def test_handshake_succeeds_and_advertises_both_tools() -> None:
    listing, _ = run()
    names = {tool.name for tool in listing.tools}
    assert "check_flight_readiness" in names
    assert "get_drone_maintenance_status" in names


def test_maintenance_tool_answers_over_the_protocol() -> None:
    _, result = run("get_drone_maintenance_status", {"drone": "NTU Sim Drone A"})
    payload = json.loads(result.content[0].text)
    assert payload["status"] == "OK"
    assert payload["drone_name"] == "NTU Sim Drone A"


def test_simulated_data_is_labelled_over_the_protocol() -> None:
    # The label has to survive serialisation, not just exist in-process.
    _, result = run("get_drone_maintenance_status", {"drone": "NTU Sim Drone C"})
    payload = json.loads(result.content[0].text)
    assert payload["status"] == "OVERDUE"
    assert payload["data_source"] == "simulated_fleet"
    assert "SIMULATED" in payload["assumptions"][0]


def test_unknown_drone_returns_a_readable_error_not_a_crash() -> None:
    # A tool must never take down the conversation; it returns NEEDS_INFO.
    _, result = run("get_drone_maintenance_status", {"drone": "Nonexistent Drone"})
    payload = json.loads(result.content[0].text)
    assert payload["status"] == "NEEDS_INFO"
    assert payload["missing_inputs"]


def test_tool_descriptions_reach_the_client() -> None:
    # The description is how the model selects the tool, so it has to survive
    # the protocol, not just exist as a docstring.
    listing, _ = run()
    tools = {tool.name: tool for tool in listing.tools}

    readiness = tools["check_flight_readiness"].description or ""
    assert "safely fly" in readiness.lower()
    assert "read-only" in readiness.lower()

    maintenance = tools["get_drone_maintenance_status"].description or ""
    assert "due for maintenance" in maintenance.lower()


def test_input_schemas_are_advertised() -> None:
    listing, _ = run()
    tools = {tool.name: tool for tool in listing.tools}
    maintenance = tools["get_drone_maintenance_status"].inputSchema
    assert "drone" in (maintenance.get("properties") or {})
    readiness = tools["check_flight_readiness"].inputSchema
    assert "request" in (readiness.get("properties") or {})


def test_no_stray_output_corrupts_the_stream() -> None:
    # If any import or call printed to stdout, the handshake above would have
    # failed. Two sequential calls prove the stream stays clean after use.
    _, first = run("get_drone_maintenance_status", {"drone": "NTU Sim Drone A"})
    _, second = run("get_drone_maintenance_status", {"drone": "NTU Sim Drone B"})
    assert json.loads(first.content[0].text)["status"] == "OK"
    assert json.loads(second.content[0].text)["status"] == "DUE_SOON"
