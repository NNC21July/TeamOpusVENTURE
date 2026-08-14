from mcp.server.fastmcp.server import FastMCP

import api_client.rest_client as rest_client
from tools.get_live_telemetry import get_live_telemetry

mcp = FastMCP("Team-Opus MCP Server")

# Fields we surface to the model. Deliberately excludes user identifiers
# (created_by / last_modified_by), internal ids (company_id / provider_id),
# and the free-text `properties` blob — data minimization plus keeping an
# untrusted free-text field out of the model's view.
_DRONE_FIELDS = ("name", "serial_number", "drone_model_id", "status", "serviceable", "drone_id")


def _shape_drones(data: object) -> dict:
    """Trim the raw /aircraft/drones payload down to the fields that answer the question."""
    if isinstance(data, dict):
        drones = data.get("drones", [])
    elif isinstance(data, list):
        drones = data
    else:
        drones = []
    trimmed = [
        {field: drone.get(field) for field in _DRONE_FIELDS}
        for drone in drones
        if isinstance(drone, dict)
    ]
    return {"count": len(trimmed), "drones": trimmed}


@mcp.tool()
def testing_tool(test_string: str) -> str:
    """
    A simple test tool that returns a string when called.
    This can be used to verify that the MCP server is functioning correctly and that tools can be registered
    and executed without issues.
    """
    return f'Received string: {test_string}'


@mcp.tool()
def list_drones() -> dict:
    """
    List the drones in the fleet with their key status fields.

    Use this to answer questions like "what drones do we have?", "which drones are
    active?", or to find a drone's serial number or id before another call. Returns
    each drone's name, serial number, model id, status, whether it is serviceable,
    and its drone_id (reuse the id in follow-up calls). Read-only: it only reads
    fleet data and changes nothing.
    """
    try:
        data = rest_client.get_drones()
    except rest_client.APIError as exc:
        return {"error": str(exc)}
    return _shape_drones(data)

@mcp.tool()
async def get_live_telemetry(drone_id: str, limit: int = 3, timeout_seconds: float = 5.0) -> dict:
    """
    Collect a small telemetry snapshot from the live WebSocket for a specific drone.

    Args:
        drone_id (str): The unique identifier of the drone.
        limit (int): The maximum number of telemetry messages to collect. Default is 3.
        timeout_seconds (float): The maximum time to wait for each message in seconds. Default is 5.0.

    Use this to answer questions like "what is the current telemetry for drone X?" or to get a quick snapshot of the drone's state. 
    Returns a dictionary containing the status of the operation, the drone_id, the count of messages received, and the messages themselves. 
    If an error occurs, it returns an error message.
    """
    return await get_live_telemetry(drone_id, limit=limit, timeout_seconds=timeout_seconds)


if __name__ == "__main__":
    mcp.run(transport="stdio")