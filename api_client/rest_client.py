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

NOTE: MEDIA_BASE_URL and the flight->media linkage query param are our best
guess pending confirmation from Garuda (Full_Media.flight_id is deprecated;
see Research 2). GEO_AI_BASE_URL is taken directly from the Geo AI Config
Service OAS docs. Both should be double-checked against the live sandbox
before this is relied on for a demo.
"""

from __future__ import annotations

from typing import Any

import httpx

import auth

BASE_URL = "https://api.mydronefleets.com"
MEDIA_BASE_URL = "https://media.mydronefleets.com"
GEO_AI_BASE_URL = "https://api.mydronefleets.com/airspace"
_TIMEOUT = 20.0


class APIError(Exception):
    """A Garuda API call did not succeed. Message is safe to surface."""


def _handle_response(response: httpx.Response, path: str) -> Any:
    """Shared envelope parsing for both GET and multipart-POST calls."""
    try:
        body = response.json()
    except ValueError:
        raise APIError(f"{path} returned non-JSON (HTTP {response.status_code})")

    # Standard Garuda envelope: {"status": "success"|"fail"|"error", ...}
    if isinstance(body, dict):
        status = body.get("status")
        if status == "success":
            return body.get("data")
        if status in ("fail", "error"):
            detail = body.get("message") or body.get("data")
            raise APIError(f"{path} failed (HTTP {response.status_code}): {detail}")

    # Some endpoints may not wrap; accept any 2xx body.
    if response.is_success:
        return body
    raise APIError(f"{path}: unexpected response (HTTP {response.status_code})")


def _token() -> str:
    """Fetch the bearer token, surfacing auth failures as APIError.

    Callers only ever have to handle APIError, so an identity/token outage
    returns a clean message instead of crashing the tool call.
    """
    try:
        return auth.get_token()
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
        response = httpx.get(f"{base_url}{path}", headers=headers, params=params, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise APIError(f"network error calling {path}: {exc}") from exc

    # Token may have expired mid-life; refresh once and retry.
    if response.status_code == 401 and not _retried:
        auth.get_token(force_refresh=True)
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
        auth.get_token(force_refresh=True)
        return _post_multipart(path, files=files, data=data, _retried=True, base_url=base_url)

    return _handle_response(response, path)


def get_drones(params: dict[str, Any] | None = None) -> Any:
    """GET /aircraft/drones — the fleet's drones. Returns the raw `data` payload."""
    return _get("/aircraft/drones", params=params)

def get_nfzs(params: dict[str, Any] | None = None) -> Any:
    """GET /airspace/nfzs — the fleet's NFZs. Returns the raw `data` payload."""
    return _get("/airspace/nfzs", params=params)


def get_media_for_flight(flight_id: str) -> Any:
    """GET media associated with a flight, via the Media Asset Service.

    UNCONFIRMED: Full_Media.flight_id is documented as deprecated, so the
    query param / endpoint below is a placeholder pending Garuda confirming
    the current flight -> media linkage (see Research 2, "Still to Research").
    Update this once confirmed rather than assuming it works as written.
    """
    return _get("/media", params={"flight_id": flight_id}, base_url=MEDIA_BASE_URL)


def get_media_bytes(url: str) -> bytes:
    """Download a media item's raw bytes from its Media Asset Service URL.

    Needed because /ml_detections/upload takes a raw image, not a media_id
    reference — see Research 2, "Resolved: upload takes raw image, not
    media_id". This is a plain authenticated fetch, not through `_get`,
    since the response here is binary, not the standard JSON envelope.
    """
    headers = {"Authorization": f"Bearer {_token()}"}
    try:
        response = httpx.get(url, headers=headers, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise APIError(f"network error fetching media bytes from {url}: {exc}") from exc

    if response.status_code == 401:
        headers = {"Authorization": f"Bearer {auth.get_token(force_refresh=True)}"}
        try:
            response = httpx.get(url, headers=headers, timeout=_TIMEOUT)
        except httpx.HTTPError as exc:
            raise APIError(f"network error fetching media bytes from {url}: {exc}") from exc

    if not response.is_success:
        raise APIError(f"fetching media bytes failed (HTTP {response.status_code}): {url}")
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
        auth.get_token(force_refresh=True)
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
        auth.get_token(force_refresh=True)
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
            preview = {k: d0.get(k) for k in ("name", "serial_number", "model", "status", "drone_id", "id") if k in d0}
            print("sample (non-personal):", preview)
    else:
        print("unexpected shape; repr head:", repr(data)[:300])
