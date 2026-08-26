"""Minimal Garuda Plex REST client.

A thin wrapper over httpx that attaches the bearer token from `auth`, targets a
Garuda REST base, understands the standard response envelope, and refreshes the
token once on a 401. It returns parsed data on success and raises `APIError` on
failure so callers (the MCP tools) can catch it and return a clean message
instead of crashing the conversation.

Base URLs and endpoints are per the Developer Programme onboarding and the
shared tool contract. Encapsulation: MCP tools call these helpers and never
touch auth or HTTP directly.

Three services are covered here, each with its own base URL:
  - Aircraft/Fleet Service   (BASE_URL)       — e.g. /aircraft/drones
  - Media Asset Service      (MEDIA_BASE_URL) — flight media (images/video)
  - Geo AI Config Service    (GEO_AI_BASE_URL) — ML detections

NOTE (updated 2026-08-24, after probing the live sandbox + the Media Service
and Geo AI Config Service Swagger docs):
  - Media metadata fetch-by-id works via BASE_URL: /media/{media_id}
    (confirmed live). The Media Service's own documented server is
    MEDIA_BASE_URL with path /m/{media_id} — same schema, so BASE_URL's
    /media/{id} is presumably a gateway alias for it. Left as BASE_URL since
    that's the proven-working path; MEDIA_BASE_URL is used for the
    size-variant binary endpoints below, which only exist on that host.
  - CONFIRMED: there is no download URL anywhere on the Media object itself.
    Binary bytes come from GET {MEDIA_BASE_URL}/m/{media_id}/{variant}
    (variant = thumb/preview/medium/large/fullscreen/original) — see
    get_media_bytes.
  - The flight -> media *listing* linkage is still unresolved, and now more
    specifically: the Media Service Swagger has NO list/query endpoint at
    all (only fetch-by-known-id and the size variants). get_media_for_flight
    below is confirmed NOT to work as written (404). The real linkage is
    more likely via the Building Facade Inspection Ops API (Inspection ->
    images), not the Media Service directly — that Swagger hasn't been
    pulled yet.
  - RESOLVED (2026-08-25, Inspection Ops Service Swagger): the flight ->
    media link and the missing upload endpoint were both a wrong-service
    problem, not missing functionality. Facade-inspection media is NOT
    reached through the Media Service at all — the real chain is:
    Inspection.flight_ids[] (GET /inspections, INSPECTION_BASE_URL) -> each
    inspection's images (GET /images, filtered by inspection_id — exact
    query param unverified live) -> each image's media_id -> plugs directly
    into the already-working get_media_by_id/get_media_bytes. Upload is
    POST /images (INSPECTION_BASE_URL): multipart, takes inspection_id +
    file, uploads to the Media Service AND associates it with the
    inspection in one call — this is the real create/upload path.
  - GEO_AI_BASE_URL is confirmed correct (https://api.mydronefleets.com/airspace,
    per that service's own Swagger "Servers" section) — but whether
    /ml_detections/upload actually runs inference given a raw image, vs.
    only persisting detections computed elsewhere, is still unconfirmed.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

import auth

BASE_URL = "https://api.mydronefleets.com"
MEDIA_BASE_URL = "https://media.mydronefleets.com"
GEO_AI_BASE_URL = "https://api.mydronefleets.com/airspace"
INSPECTION_BASE_URL = "https://api.mydronefleets.com/inspection-ops"
_TIMEOUT = 20.0


class APIError(Exception):
    """A Garuda API call did not succeed. Message is safe to surface."""


def _handle_response(response: httpx.Response, path: str) -> Any:
    """Shared envelope parsing for both GET and multipart-POST calls."""
    try:
        body = response.json()
    except ValueError:
        raise APIError(
            f"{path} returned non-JSON (HTTP {response.status_code})")

    # Standard Garuda envelope: {"status": "success"|"fail"|"error", ...}
    if isinstance(body, dict):
        status = body.get("status")
        if status == "success":
            return body.get("data")
        if status in ("fail", "error"):
            detail = body.get("message") or body.get("data")
            raise APIError(
                f"{path} failed (HTTP {response.status_code}): {detail}")

    # Some endpoints may not wrap; accept any 2xx body.
    if response.is_success:
        return body
    raise APIError(
        f"{path}: unexpected response (HTTP {response.status_code})")


def _token(force_refresh: bool = False) -> str:
    """Fetch the bearer token, surfacing auth failures as APIError.

    Callers only ever have to handle APIError, so an identity/token outage
    returns a clean message instead of crashing the tool call.
    """
    try:
        return auth.get_token(force_refresh=force_refresh)
    except auth.AuthError as exc:
        raise APIError(f"authentication failed: {exc}") from exc


def _get(
    path: str,
    params: dict[str, Any] | None = None,
    _retried: bool = False,
    base_url: str = BASE_URL,
) -> Any:
    headers = {"Authorization": f"Bearer {_token()}"}
    try:
        response = httpx.get(
            f"{base_url}{path}", headers=headers, params=params, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise APIError(f"network error calling {path}: {exc}") from exc

    # Token may have expired mid-life; refresh once and retry.
    if response.status_code == 401 and not _retried:
        _token(force_refresh=True)
        return _get(path, params=params, _retried=True, base_url=base_url)

    return _handle_response(response, path)


def _post_multipart(
    path: str,
    *,
    files: dict[str, Any],
    data: dict[str, Any] | None = None,
    _retried: bool = False,
    base_url: str = BASE_URL,
) -> Any:
    """POST a multipart/form-data request (e.g. an image upload).

    Mirrors `_get`'s auth/retry/envelope handling so callers get the same
    APIError behaviour regardless of which verb/content-type is used.
    """
    headers = {"Authorization": f"Bearer {_token()}"}
    try:
        response = httpx.post(
            f"{base_url}{path}", headers=headers, files=files, data=data, timeout=_TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise APIError(f"network error calling {path}: {exc}") from exc

    if response.status_code == 401 and not _retried:
        _token(force_refresh=True)
        return _post_multipart(path, files=files, data=data, _retried=True, base_url=base_url)

    return _handle_response(response, path)


def get_drones(params: dict[str, Any] | None = None) -> Any:
    """GET /aircraft/drones — the fleet's drones. Returns the raw `data` payload."""
    return _get("/aircraft/drones", params=params)


def get_nfzs(params: dict[str, Any] | None = None) -> Any:
    """GET /airspace/nfzs — the fleet's NFZs. Returns the raw `data` payload."""
    return _get("/airspace/nfzs", params=params)


def get_flights(params: dict[str, Any] | None = None) -> Any:
    """GET /aircraft/flights — recorded flights. Returns the raw `data` payload."""
    return _get("/aircraft/flights", params=params)


def get_media_by_id(media_id: str) -> Any:
    """GET /media/{media_id} — one media item's metadata. CONFIRMED working."""
    return _get(f"/media/{media_id}")


def get_media_for_flight(flight_id: str) -> Any:
    # CONFIRMED (2026-08-24, live probe): bare "/media" 301-redirects to
    # "/media/?flight_id=...". Call the trailing-slash path directly rather
    # than following the redirect — the redirect's Location header comes
    # back as http:// (not https://), and since it's the same host, httpx
    # would resend the Authorization header over plaintext on a followed
    # redirect. The flight_id query param itself was correct.
    return _get("/media/", params={"flight_id": flight_id})


_MEDIA_VARIANTS = ("thumb", "preview", "medium", "large", "fullscreen", "original")


def get_media_bytes(media_id: str, variant: str = "fullscreen") -> bytes:
    """Download one size-variant of a media item's raw bytes.

    CONFIRMED against the Media Service Swagger: GET /m/{media_id}/{variant}
    returns the file directly as application/octet-stream — there is no
    separate "url" field on the Media object to read first. "original" is
    explicitly documented as huge and not for routine use; "fullscreen"
    (max 1280px) is the largest practical size for vision-model input.

    This is a plain authenticated fetch, not through `_get`, since the
    response here is binary, not the standard JSON envelope.
    """
    if variant not in _MEDIA_VARIANTS:
        raise APIError(f"unknown media variant '{variant}', must be one of {_MEDIA_VARIANTS}")

    url = f"{MEDIA_BASE_URL}/m/{media_id}/{variant}"
    headers = {"Authorization": f"Bearer {_token()}"}
    try:
        response = httpx.get(url, headers=headers, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise APIError(
            f"network error fetching media bytes from {url}: {exc}") from exc

    if response.status_code == 401:
        headers = {
            "Authorization": f"Bearer {_token(force_refresh=True)}"}
        try:
            response = httpx.get(url, headers=headers, timeout=_TIMEOUT)
        except httpx.HTTPError as exc:
            raise APIError(
                f"network error fetching media bytes from {url}: {exc}") from exc

    if not response.is_success:
        raise APIError(
            f"fetching media bytes failed (HTTP {response.status_code}): {url}")
    return response.content


def create_detections(
    *, image_bytes: bytes, filename: str, labels: list[str], created_by: str
) -> Any:
    """POST /ml_detections/upload — run detection on an image / video freeze frame.

    Only still images are supported per Geo AI's docs (confirmed in Research
    2) — video needs frame extraction before calling this, which is not yet
    implemented (see "Still to Research": video frame-sampling approach).
    """
    files = {"image": (filename, image_bytes, "application/octet-stream")}
    data = {"labels": labels, "created_by": created_by}
    return _post_multipart("/ml_detections/upload", files=files, data=data, base_url=GEO_AI_BASE_URL)


def get_detections(params: dict[str, Any] | None = None) -> Any:
    """GET /ml_detections — query detections that already exist, without re-running inference."""
    return _get("/ml_detections", params=params, base_url=GEO_AI_BASE_URL)


def get_facilities(params: dict[str, Any] | None = None) -> Any:
    """GET /facilities (Inspection Ops Service) — query facilities.

    An Inspection requires a facility_id, so this is checked before
    creating a new Facility for test data — reusing an existing one avoids
    guessing at POST /facilities's request schema, which hasn't been seen
    expanded yet.
    """
    return _get("/facilities", params=params, base_url=INSPECTION_BASE_URL)


def create_facility(payload: dict[str, Any]) -> Any:
    """POST /facilities (Inspection Ops Service) — create a Facility.

    A Facility is a prerequisite for creating an Inspection (which requires
    a facility_id) — see Create_Facility schema on the Inspection Ops
    Service Swagger for the full field list.
    """
    return _post_json("/facilities", payload, base_url=INSPECTION_BASE_URL)


def create_inspection(payload: dict[str, Any]) -> Any:
    """POST /inspections (Inspection Ops Service) — create an Inspection.

    payload["flight_ids"] is the real link back to a Flight — this is what
    makes GarudaMediaClient.get_media_for_flight's Inspection lookup find
    it later. See Create_Inspection schema on the Inspection Ops Service
    Swagger for the full field list.
    """
    return _post_json("/inspections", payload, base_url=INSPECTION_BASE_URL)


def get_facility_elevations(params: dict[str, Any] | None = None) -> Any:
    """GET /elevations (Inspection Ops Service) — query Facility Elevations."""
    return _get("/elevations", params=params, base_url=INSPECTION_BASE_URL)


def create_facility_elevation(payload: dict[str, Any]) -> Any:
    """POST /elevations (Inspection Ops Service) — create a Facility Elevation.

    A Facility Elevation is a prerequisite for POST /images's
    facility_elevations reference — see create_inspection_image.
    """
    return _post_json("/elevations", payload, base_url=INSPECTION_BASE_URL)


def update_inspection(inspection_id: str, payload: dict[str, Any]) -> Any:
    """PATCH /inspections/{inspection_id} (Inspection Ops Service)."""
    return _patch_json(f"/inspections/{inspection_id}", payload, base_url=INSPECTION_BASE_URL)


def get_inspections(params: dict[str, Any] | None = None) -> Any:
    """GET /inspections (Inspection Ops Service) — query inspections.

    Each inspection carries flight_ids[] — CONFIRMED (Inspection Ops Service
    Swagger) this is the real link from a Flight to its facade-inspection
    media. The Media Service itself has no flight linkage at all.
    """
    return _get("/inspections", params=params, base_url=INSPECTION_BASE_URL)


def get_inspection_images(params: dict[str, Any] | None = None) -> Any:
    """GET /images (Inspection Ops Service) — query inspection images.

    CONFIRMED live (2026-08-26): the filter param is inspection_ids
    (PLURAL) and is required — "inspection_id" (singular) is rejected as
    an unknown param, and omitting the filter entirely is rejected as
    missing a required property. Pass a list; httpx serialises it as
    repeated query params.
    """
    return _get("/images", params=params, base_url=INSPECTION_BASE_URL)


def create_inspection_image(
    *,
    inspection_id: str,
    image_bytes: bytes,
    filename: str,
    facility_elevation: list[str] | None = None,
    privacy_mask: bool | None = None,
) -> Any:
    """POST /images (Inspection Ops Service) — upload an image.

    Uploads to the Media Service and associates the resulting media_id with
    the given inspection in one call. This is the real create/upload path —
    the Media Service itself has no upload endpoint at all.
    """
    files = {"file": (filename, image_bytes, "application/octet-stream")}
    data: dict[str, Any] = {"inspection_id": inspection_id}
    if facility_elevation:
        # CONFIRMED (2026-08-26) via a known-working request sample from
        # Garuda: the real field name is "facility_elevations" (PLURAL) —
        # the Swagger docs document it as singular ("facility_elevation"),
        # which is simply wrong/stale. Value is a JSON-stringified array,
        # e.g. '["6a713e4a565896c2d3961487"]', no brackets on the field name.
        # This is what every earlier "Invalid facility_elevations" rejection
        # was actually about — wrong field name, not a format/encoding issue.
        data["facility_elevations"] = json.dumps(facility_elevation)
    if privacy_mask is not None:
        data["privacy_mask"] = str(privacy_mask).lower()
    return _post_multipart("/images", files=files, data=data, base_url=INSPECTION_BASE_URL)


def _post_json(
    path: str,
    json_body: dict[str, Any] | None = None,
    _retried: bool = False,
    base_url: str = BASE_URL,
) -> Any:
    """POST a JSON body. Mirrors `_get`'s auth/retry/envelope handling."""
    headers = {"Authorization": f"Bearer {_token()}"}
    try:
        response = httpx.post(
            f"{base_url}{path}", headers=headers, json=json_body, timeout=_TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise APIError(f"network error calling {path}: {exc}") from exc

    if response.status_code == 401 and not _retried:
        _token(force_refresh=True)
        return _post_json(path, json_body=json_body, _retried=True, base_url=base_url)

    return _handle_response(response, path)


def _patch_json(
    path: str,
    json_body: dict[str, Any],
    _retried: bool = False,
    base_url: str = BASE_URL,
) -> Any:
    """PATCH a JSON body. Mirrors `_get`'s auth/retry/envelope handling."""
    headers = {"Authorization": f"Bearer {_token()}"}
    try:
        response = httpx.patch(
            f"{base_url}{path}", headers=headers, json=json_body, timeout=_TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise APIError(f"network error calling {path}: {exc}") from exc

    if response.status_code == 401 and not _retried:
        _token(force_refresh=True)
        return _patch_json(path, json_body, _retried=True, base_url=base_url)

    return _handle_response(response, path)


def get_drone(drone_id: str) -> dict:
    """GET /aircraft/drones/{drone_id} - one drone's full record."""
    data = _get(f"/aircraft/drones/{drone_id}")
    if isinstance(data, dict):
        # The endpoint may nest the record under "drone".
        return data.get("drone", data)
    raise APIError(f"unexpected drone payload for {drone_id}")


# --- State-changing calls ----------------------------------------------------
# These are what the governance gate exists to protect.
#
# UNVERIFIED against the live sandbox. The paths come from the Developer
# Programme onboarding deck (slide 33), which gives them relative to the
# LiveFlights service. As of 20 Aug the service does not answer for our
# credentials: /liveflights/sanity 404s while /aircraft/sanity is fine, and
# POST .../arm returns 404. Either LiveFlights is not enabled for the
# Developer Programme, or arm/takeoff only exist once a drone is in an active
# live-flight session (the deck requires the drone powered, GPS-fixed and RTF).
# Confirm with Garuda before relying on these for a demo; use set_drone_property
# for a write that is known to work end to end.

def arm_drone(drone_id: str) -> Any:
    """POST /liveflights/drone/{drone_id}/arm - arms the motors. Real action."""
    return _post_json(f"/liveflights/drone/{drone_id}/arm")


def takeoff_drone(drone_id: str) -> Any:
    """POST /liveflights/drone/{drone_id}/takeoff - the drone leaves the ground."""
    return _post_json(f"/liveflights/drone/{drone_id}/takeoff")


def land_drone(drone_id: str) -> Any:
    """POST /liveflights/drone/{drone_id}/land - the undo for takeoff."""
    return _post_json(f"/liveflights/drone/{drone_id}/land")


def set_drone_property(drone_id: str, key: str, value: Any) -> Any:
    """Merge one key into a drone's `properties` and PATCH it back.

    Read-modify-write on purpose: `properties` already carries fields such as
    {"simulated": true}, and PATCHing a bare {key: value} would drop them.
    """
    drone = get_drone(drone_id)
    properties = dict(drone.get("properties") or {})
    properties[key] = value
    return _patch_json(f"/aircraft/drones/{drone_id}", {"properties": properties})


if __name__ == "__main__":
    # Safe shape probe: prints structure and non-personal drone fields only.
    try:
        data = get_drones()
    except APIError as exc:
        print("API error:", exc)
        raise SystemExit(1)

    print("data type:", type(data).__name__)
    drones = data
    if isinstance(data, dict):
        print("top-level keys:", list(data.keys()))
        for key in ("drones", "results", "items", "data"):
            if isinstance(data.get(key), list):
                drones = data[key]
                print("list is under key:", key)
                break

    if isinstance(drones, list):
        print("drone count:", len(drones))
        if drones and isinstance(drones[0], dict):
            print("first drone field names:", list(drones[0].keys()))
            d0 = drones[0]
            preview = {k: d0.get(k) for k in (
                "name", "serial_number", "model", "status", "drone_id", "id") if k in d0}
            print("sample (non-personal):", preview)
    else:
        print("unexpected shape; repr head:", repr(data)[:300])
