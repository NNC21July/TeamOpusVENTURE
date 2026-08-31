from datetime import datetime, timezone

from mcp.server.fastmcp.server import FastMCP

from api_client import rest_client
from governance import approvals
from governance.gate import governed
from tools.vision_summarizer.annotation_import import (
    parse_csv_rows,
    parse_yolo_file,
    rows_for_filename,
    rows_to_raw_detections,
    yolo_rows_to_raw_detections,
)
from tools.vision_summarizer.garuda_detection_client import GarudaDetectionClient
from tools.vision_summarizer.garuda_media_client import GarudaMediaClient
from tools.vision_summarizer.request_response_schemas import MediaItem, SummarizeFlightRequest
from tools.vision_summarizer.service import summarize_flight
from tools.route_airspace_compliance.garuda_airspace_client import GarudaAirspaceClient
from tools.route_airspace_compliance.output_shaper import shape_route_compliance_response
from tools.route_airspace_compliance.request_response_schemas import RouteComplianceRequest
from tools.route_airspace_compliance.service import check_route_airspace_compliance as evaluate_route_airspace_compliance
from tools import demo_fleet
from tools.flight_readiness.demo_client import DemoAircraftClient
from tools.flight_readiness.garuda_aircraft_client import GarudaAircraftClient
from tools.flight_readiness.output_shaper import shape_flight_readiness_response
from tools.flight_readiness.request_response_schemas import FlightReadinessRequest
from tools.flight_readiness.service import check_flight_readiness as evaluate_flight_readiness
from tools.flight_readiness.sources.nea_client import NeaClient
from tools.flight_readiness.sources.open_meteo_client import OpenMeteoClient
from tools.maintenance_status.demo_client import DemoMaintenanceClient
from tools.maintenance_status.garuda_maintenance_client import GarudaMaintenanceClient
from tools.maintenance_status.output_shaper import shape_maintenance_status_response
from tools.maintenance_status.readiness_bridge import MaintenanceStatusReader
from tools.maintenance_status.request_response_schemas import MaintenanceStatusRequest
from tools.maintenance_status.service import get_drone_maintenance_status as evaluate_maintenance_status

mcp = FastMCP("Team-Opus MCP Server")

# Fields we surface to the model. Deliberately excludes user identifiers
# (created_by / last_modified_by), internal ids (company_id / provider_id),
# and the free-text `properties` blob — data minimization plus keeping an
# untrusted free-text field out of the model's view.
_DRONE_FIELDS = ("name", "serial_number", "drone_model_id",
                 "status", "serviceable", "drone_id")


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
@governed("testing_tool")
def testing_tool(test_string: str, approval_request_id: str | None = None) -> dict:
    """
    A simple test tool that returns a string when called.
    This can be used to verify that the MCP server is functioning correctly and that tools can be registered
    and executed without issues.
    """
    return {"received": test_string}


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


def _shape_flights(data: object) -> dict:
    """Trim the raw /aircraft/flights payload to what identifies a flight.

    Deliberately drops `pilots` (real names and usernames — personal data that
    must not reach the model or the logs) and `location` (free text we do not
    neutralise yet, and it carries no useful value in the sandbox).
    """
    flights = data.get("flights", []) if isinstance(data, dict) else data
    if not isinstance(flights, list):
        flights = []

    trimmed = []
    for flight in flights:
        if not isinstance(flight, dict):
            continue
        # `date` is epoch milliseconds, or -1 when the flight has no date set.
        raw_date = flight.get("date")
        flown_on = None
        if isinstance(raw_date, (int, float)) and raw_date > 0:
            flown_on = datetime.fromtimestamp(
                raw_date / 1000).isoformat(timespec="seconds")

        # `duration` is split across hours/minutes/seconds, and the keys vary.
        # Sum it here rather than leaving the model to do arithmetic.
        duration = flight.get("duration") or {}
        duration_s = (
            (duration.get("hours") or 0) * 3600
            + (duration.get("minutes") or 0) * 60
            + (duration.get("seconds") or 0)
        ) if isinstance(duration, dict) else None

        trimmed.append({
            "flight_id": flight.get("flight_id"),
            "status": flight.get("status"),
            "drone_name": (flight.get("drone") or {}).get("name"),
            "flown_on": flown_on,
            "duration_seconds": duration_s,
        })
    return {"count": len(trimmed), "flights": trimmed}


@mcp.tool()
def list_flights() -> dict:
    """
    List recorded flights, most useful for finding a flight_id.

    Use this to answer "what flights do we have?", "which flights has Sim Drone A
    made?", or to find the flight_id needed by summarize_flight_inspection.
    Returns each flight's id, status (preflight/flying/postflight), the drone that
    flew it, when it flew, and how long it lasted. Read-only: it only reads flight
    records and changes nothing.
    """
    try:
        data = rest_client.get_flights()
    except rest_client.APIError as exc:
        return {"error": str(exc)}
    return _shape_flights(data)


@mcp.tool()
def check_approval_status(request_id: str) -> dict:
    """
    Check whether a pending action has been approved or denied by a pilot yet.

    Use this after telling the pilot to run approve.py, so you can see what
    actually happened instead of retrying blind. Returns the action's status:
      PENDING  — nobody has decided yet; the pilot still needs to run approve.py
      APPROVED — retry the original tool with approval_request_id set to this id
      DENIED   — the pilot refused; do not retry, tell them it was denied
      CONSUMED — already used; approvals are single-use, so a new one is needed

    Read-only: this only reads the approval record. It cannot approve anything —
    only a human running approve.py in a terminal can do that.
    """
    request = approvals.get_request(request_id)
    if request is None:
        return {
            "error": f"No approval request with id {request_id}.",
            "hint": "The id may be wrong, or the action was never proposed.",
        }

    next_step = {
        "PENDING": "Not approved yet. The pilot must run 'python approve.py "
                   f"approve {request_id} <their_pilot_id>' in a terminal.",
        "APPROVED": "Approved. Call the original tool again with identical "
                    f"arguments plus approval_request_id='{request_id}'.",
        "DENIED": "The pilot denied this. Do not retry it.",
        "CONSUMED": "Already executed. Approvals are single-use; propose the "
                    "action again if it needs to happen once more.",
    }[request.status.value]

    return {
        "request_id": request.request_id,
        "action": request.preview,
        "status": request.status.value,
        "decided_by": request.pilot_id,
        "next_step": next_step,
    }


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
def summarize_flight_inspection(
    flight_id: str, focus: str | None = None, reference_label: str | None = None
) -> dict:
    """
    Summarize what was captured during a flight's facade inspection.

    Given a flight_id, retrieves the flight's media, runs it through Garuda's
    Geo AI detection, and returns deduplicated, plain-language-described
    findings (what was detected, roughly where in the frame). Pass
    focus="defects only" to narrow findings to defect-type detections when
    writing your summary.

    reference_label: the label (if any) this inspection's annotate.garuda.io
    project uses for a structural reference object (e.g. "facade" or
    "window") — there is no fixed taxonomy to guess from, every project
    defines its own labels, so this can only come from whoever set up that
    project. If you don't know it, leave this unset: findings are still
    returned in full, just without a `relation` description relative to
    anything. If given but no detection actually has that label, it's
    silently ignored — every detection is still reported normally.

    Video media: currently summarized from a single representative frame
    only, not the full video — findings from video will have a note saying
    so, and the response status will be PARTIAL rather than COMPLETE.

    This tool does NOT write the final prose summary for you — use the
    returned findings to write a short, pilot-readable summary yourself.
    Always state the returned status (COMPLETE / PARTIAL / NO_MEDIA /
    NEEDS_INFO / UNKNOWN) and pass along any notes, so the pilot knows
    whether they're seeing the full picture. Read-only: it only reads
    flight/media/detection data and changes nothing.
    """
    request = SummarizeFlightRequest(flight_id=flight_id, focus=focus, reference_label=reference_label)
    response = summarize_flight(
        request=request,
        media_client=GarudaMediaClient(),
        detection_client=GarudaDetectionClient(),
    )
    return _shape_summary(response)


class _DemoMediaClient:
    """One-off stand-in for demo_summarize_flight_inspection_from_csv — not
    the shared test double in tests/fakes.py, so this tool has no import
    dependency on the test suite."""

    def __init__(self, media_items: list) -> None:
        self._media_items = media_items

    def get_media_for_flight(self, *, flight_id: str) -> list:
        return list(self._media_items)


class _DemoDetectionClient:
    def __init__(self, detections: list) -> None:
        self._detections = detections

    def get_detections_for_media(self, *, media) -> list:
        return list(self._detections)


@mcp.tool()
def demo_summarize_flight_inspection_from_csv(
    csv_path: str,
    image_filename: str,
    flight_id: str = "DEMO-FLIGHT",
    reference_label: str | None = None,
) -> dict:
    """
    DEMO ONLY — summarize a facade inspection from a local annotation CSV,
    with no live Garuda calls at all.

    Use this instead of summarize_flight_inspection while the Inspection Ops
    / Geo AI services are unavailable, or while Garuda's create_detections
    labels-format bug is unresolved (see rest_client.py) — this tool never
    calls either service.

    csv_path: path to a bbox annotation CSV, rows shaped
        label,x,y,w,h,filename,image_width,image_height (pixel bbox values).
    image_filename: which image's rows to use from that CSV.
    flight_id: label only for the returned summary — not looked up anywhere.
    reference_label: which label in THIS CSV (if any) is a structural
        reference object rather than a defect — e.g. "facade". Only set this
        if that label is actually present in the CSV; annotate.garuda.io's
        label taxonomy is project-specific, so there's nothing to guess here.

    Read-only, reads only the local CSV file. This is NOT the production
    path: it bypasses GarudaMediaClient/GarudaDetectionClient entirely and
    exists to demo the synthesis step. Remove once the real pipeline
    (annotations uploaded live, summarize_flight_inspection reading them
    back) is confirmed working end-to-end.
    """
    rows = rows_for_filename(parse_csv_rows(csv_path), image_filename)
    if not rows:
        return {"error": f"No rows in {csv_path} match filename {image_filename!r}"}

    media_id = f"DEMO-{image_filename}"
    detections = rows_to_raw_detections(rows, media_id=media_id)
    media = MediaItem(media_id=media_id, media_type="image", captured_at=datetime.now(timezone.utc))

    response = summarize_flight(
        request=SummarizeFlightRequest(flight_id=flight_id, reference_label=reference_label),
        media_client=_DemoMediaClient([media]),
        detection_client=_DemoDetectionClient(detections),
    )
    return _shape_summary(response)


@mcp.tool()
def demo_summarize_flight_inspection_from_yolo(
    txt_path: str,
    class_names: dict[int, str],
    flight_id: str = "DEMO-FLIGHT",
    reference_label: str | None = None,
) -> dict:
    """
    DEMO ONLY — YOLO-format equivalent of demo_summarize_flight_inspection_from_csv.
    Same purpose (see that tool's docstring): no live Garuda calls, exists to
    demo the synthesis step independent of the current Inspection Ops outage
    and Geo AI upload bug.

    txt_path: path to a YOLO .txt annotation file — one line per detection,
        "class_id x_center y_center width height", already normalized [0,1].
    class_names: maps each class_id in that file to a label string, e.g.
        {0: "crack", 1: "spalling"}. A YOLO .txt file carries no label names
        itself — this MUST come from whatever classes.txt/data.yaml the
        annotation export paired with it. Never guess this mapping.
    flight_id: label only for the returned summary — not looked up anywhere.
    reference_label: which label (if any) is a structural reference object
        rather than a defect — must match one of the values in class_names.

    Read-only, reads only the local .txt file. NOT the production path.
    """
    rows = parse_yolo_file(txt_path)
    if not rows:
        return {"error": f"No rows parsed from {txt_path}"}

    unknown_ids = {row.class_id for row in rows} - set(class_names)
    if unknown_ids:
        return {"error": f"class_names has no entry for class_id(s) {sorted(unknown_ids)} found in {txt_path}"}

    filename = txt_path.rsplit("/", 1)[-1]
    media_id = f"DEMO-{filename}"
    detections = yolo_rows_to_raw_detections(rows, media_id=media_id, class_names=class_names)
    media = MediaItem(media_id=media_id, media_type="image", captured_at=datetime.now(timezone.utc))

    response = summarize_flight(
        request=SummarizeFlightRequest(flight_id=flight_id, reference_label=reference_label),
        media_client=_DemoMediaClient([media]),
        detection_client=_DemoDetectionClient(detections),
    )
    return _shape_summary(response)


@mcp.tool()
def check_route_airspace_compliance(request: RouteComplianceRequest) -> dict:
    """
    Check whether a proposed drone route conflicts with active no-fly zones.

    Provide the ordered route waypoints and the planned flight start and end
    times. Timestamps must include a timezone. The result states whether the
    route passes, is blocked, needs more information, or could not be checked.

    This tool is read-only. It does not create reservations, book airspace,
    modify a flight plan, or control a drone. FRZ checking is not implemented
    yet, so providing an frz_id may produce an UNKNOWN decision.
    """
    response = evaluate_route_airspace_compliance(
        request=request, client=GarudaAirspaceClient())
    return shape_route_compliance_response(response)


def _resolve_drone_id(drone: str) -> str:
    """Turn what a pilot says ("Sim Drone A", or a serial) into a drone_id.

    Raises ValueError with a readable message if there is no single match, so
    the calling tool can surface it instead of guessing which drone was meant.
    """
    data = rest_client.get_drones()
    drones = data.get("drones", []) if isinstance(data, dict) else data
    needle = drone.strip().lower()

    exact = [d for d in drones if str(
        d.get("serial_number", "")).lower() == needle]
    if len(exact) == 1:
        return exact[0]["drone_id"]

    matches = [d for d in drones if needle in str(d.get("name", "")).lower()]
    if len(matches) == 1:
        return matches[0]["drone_id"]
    if not matches:
        names = ", ".join(str(d.get("name")) for d in drones)
        raise ValueError(f"No drone matching {drone!r}. Available: {names}")
    names = ", ".join(str(d.get("name")) for d in matches)
    raise ValueError(
        f"{drone!r} matches several drones: {names}. Be more specific.")


# --- State-changing tools ----------------------------------------------------
# Both declare `approval_request_id` in their own signature on purpose: FastMCP
# reads the wrapped function's signature (functools.wraps), so without it the
# model never sees the parameter and cannot complete the approval retry.

@mcp.tool()
@governed("set_drone_note")
def set_drone_note(drone: str, note: str, approval_request_id: str | None = None) -> dict:
    """
    Attach a note to a drone's record in Garuda Plex.

    THIS CHANGES REAL FLEET DATA and requires pilot approval before it runs.
    Calling it without an approval returns status PENDING_APPROVAL and a
    request_id: tell the pilot to approve that request, then call this tool
    again with identical arguments plus approval_request_id set to that id.

    `drone` may be a name or serial number (e.g. "Sim Drone A").
    """
    try:
        drone_id = _resolve_drone_id(drone)
        rest_client.set_drone_property(drone_id, "note", note)
    except (rest_client.APIError, ValueError) as exc:
        return {"error": str(exc)}
    return {"status": "OK", "drone_id": drone_id, "note": note}


@mcp.tool()
@governed("takeoff")
def takeoff(drone: str, approval_request_id: str | None = None) -> dict:
    """
    Arm a drone and make it take off. THE DRONE PHYSICALLY LEAVES THE GROUND.

    This is the most dangerous action on this server and requires pilot
    approval before it runs. Calling it without an approval returns status
    PENDING_APPROVAL and a request_id: tell the pilot to approve that request,
    then call this tool again with identical arguments plus approval_request_id
    set to that id.

    `drone` may be a name or serial number (e.g. "Sim Drone A"). The drone must
    already be powered on, have a GPS fix and be ready to fly, or Garuda will
    reject the command.
    """
    try:
        drone_id = _resolve_drone_id(drone)
        arm_result = rest_client.arm_drone(drone_id)
        takeoff_result = rest_client.takeoff_drone(drone_id)
    except (rest_client.APIError, ValueError) as exc:
        return {"error": str(exc)}
    return {
        "status": "OK",
        "drone_id": drone_id,
        "armed": arm_result,
        "takeoff": takeoff_result,
    }


def _aircraft_client():
    """The real Plex client, or the seeded fleet when demo mode is on."""
    return DemoAircraftClient() if demo_fleet.demo_mode_enabled() else GarudaAircraftClient()


def _maintenance_client():
    return (
        DemoMaintenanceClient()
        if demo_fleet.demo_mode_enabled()
        else GarudaMaintenanceClient()
    )


def _tag_if_simulated(payload: dict) -> dict:
    """Mark any response built from seeded data, so it is never mistaken for real.

    The notice goes into `assumptions`, which both tools already surface, so
    the model reads it alongside every other caveat and can repeat it to the
    pilot rather than presenting simulated numbers as fact.
    """
    if not demo_fleet.demo_mode_enabled():
        return payload
    assumptions = list(payload.get("assumptions") or [])
    assumptions.insert(0, demo_fleet.SIMULATED_NOTICE)
    payload["assumptions"] = assumptions
    payload["data_source"] = "simulated_fleet"
    return payload


@mcp.tool()
def get_drone_maintenance_status(drone: str) -> dict:
    """
    Report whether a drone is due for maintenance.

    Use this to answer "is DRONE-001 due for servicing?", "when was it last
    serviced?", or "how many hours has this airframe flown?". Give the drone's
    name, serial number or id.

    Resolves the drone, sums its flight hours from recorded flights, and
    compares them against its service interval. Returns hours since service,
    the interval, hours remaining, and an overall status of OK, DUE_SOON,
    OVERDUE, NEEDS_INFO or UNKNOWN.

    Read-only: it only reads fleet and flight records and changes nothing.
    Values that could not be read from Plex are reported as null and explained
    in `assumptions` rather than guessed.
    """
    response = evaluate_maintenance_status(
        request=MaintenanceStatusRequest(drone=drone),
        client=_maintenance_client(),
        now=datetime.now(timezone.utc),
    )
    return _tag_if_simulated(shape_maintenance_status_response(response))


@mcp.tool()
def check_flight_readiness(request: FlightReadinessRequest) -> dict:
    """
    Check whether a drone can safely fly a given mission at a given time and place.

    Use this to answer "can I fly the Jurong facade job on Tuesday at 9am?",
    "is it too windy to fly right now?", or "which of our drones can fly
    tomorrow morning?". Call it once per drone or per date when comparing.

    Give the drone's name or serial, the planned start and end times (with a
    timezone), the location as longitude and latitude, and the planned altitude
    above ground in metres. Mission duration in minutes is optional and is
    derived from the flight window if omitted.

    Compares forecast or current weather against the aircraft's operating
    limits, checks battery endurance against the planned mission, and confirms
    the airframe is not overdue for service. Returns a decision of GO,
    GO_WITH_WARNINGS, NO_GO, NEEDS_INFO or UNKNOWN, with each check's observed
    values, the thresholds applied, and a confidence level.

    Read-only. It does not book airspace, reserve a flight zone, arm, launch or
    modify anything. A NO_GO means the mission should not proceed; an UNKNOWN
    means the assessment could not be completed and must not be read as
    approval.
    """
    response = evaluate_flight_readiness(
        request=request,
        aircraft_client=_aircraft_client(),
        maintenance_reader=MaintenanceStatusReader(client=_maintenance_client()),
        forecast_source=OpenMeteoClient(),
        observation_source=NeaClient(),
        now=datetime.now(timezone.utc),
    )
    return _tag_if_simulated(shape_flight_readiness_response(response))


if __name__ == "__main__":
    mcp.run(transport="stdio")
