from mcp.server.fastmcp.server import FastMCP

import api_client
from tools.vision_summarizer.garuda_detection_client import GarudaDetectionClient
from tools.vision_summarizer.garuda_media_client import GarudaMediaClient
from tools.vision_summarizer.request_response_schemas import SummarizeFlightRequest
from tools.vision_summarizer.service import summarize_flight

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
        data = api_client.get_drones()
    except api_client.APIError as exc:
        return {"error": str(exc)}
    return _shape_drones(data)


def _shape_summary(response) -> dict:
    """Convert a SummarizeFlightResponse (nested dataclasses/enums/datetimes)
    into a plain JSON-serializable dict for the MCP response."""
    return {
        "flight_id": response.flight_id,
        "status": response.status.value,
        "media_count": response.media_count,
        "findings": [
            {
                "media_id": finding.media_id,
                "captured_at": finding.captured_at.isoformat() if finding.captured_at else None,
                "detections": [
                    {
                        "object": d.object_label,
                        "confidence": d.score,
                        "position": d.position,
                        "relation": d.relation,
                        "occurrence_count": d.occurrence_count,
                        "first_seen_s": d.first_seen_s,
                        "last_seen_s": d.last_seen_s,
                    }
                    for d in finding.detections
                ],
            }
            for finding in response.findings
        ],
        "missing_inputs": list(response.missing_inputs),
        "notes": list(response.notes),
    }


@mcp.tool()
def summarize_flight_inspection(flight_id: str, focus: str | None = None) -> dict:
    """
    Summarize what was captured during a flight's facade inspection.

    Given a flight_id, retrieves the flight's media, runs it through Garuda's
    Geo AI detection, and returns deduplicated, plain-language-described
    findings (what was detected, roughly where in the frame, how it relates
    to the facade if that context is available, and how many times/how long
    it was observed for video). Pass focus="defects only" to narrow findings
    to defect-type detections when writing your summary.

    This tool does NOT write the final prose summary for you — use the
    returned findings to write a short, pilot-readable summary yourself.
    Always state the returned status (COMPLETE / PARTIAL / NO_MEDIA /
    NEEDS_INFO / UNKNOWN) so the pilot knows whether they're seeing the full
    picture. Read-only: it only reads flight/media/detection data and
    changes nothing.
    """
    request = SummarizeFlightRequest(flight_id=flight_id, focus=focus)
    response = summarize_flight(
        request=request,
        media_client=GarudaMediaClient(),
        detection_client=GarudaDetectionClient(),
    )
    return _shape_summary(response)


if __name__ == "__main__":
    mcp.run(transport="stdio")