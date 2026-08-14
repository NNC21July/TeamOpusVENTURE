"""Minimal Garuda Plex REST client.

A thin wrapper over httpx that attaches the bearer token from `auth`, targets the
Garuda REST base, understands the standard response envelope, and refreshes the
token once on a 401. It returns parsed data on success and raises `APIError` on
failure so callers (the MCP tools) can catch it and return a clean message
instead of crashing the conversation.

Base URL and the drones endpoint are per the Developer Programme onboarding and
the shared tool contract. Encapsulation: MCP tools call these helpers and never
touch auth or HTTP directly.
"""

from __future__ import annotations

from typing import Any

import httpx

import auth

BASE_URL = "https://api.mydronefleets.com"
_TIMEOUT = 20.0


class APIError(Exception):
    """A Garuda API call did not succeed. Message is safe to surface."""


def _get(path: str, params: dict[str, Any] | None = None, _retried: bool = False) -> Any:
    headers = {"Authorization": f"Bearer {auth.get_token()}"}
    try:
        response = httpx.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise APIError(f"network error calling {path}: {exc}") from exc

    # Token may have expired mid-life; refresh once and retry.
    if response.status_code == 401 and not _retried:
        auth.get_token(force_refresh=True)
        return _get(path, params=params, _retried=True)

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


def get_drones(params: dict[str, Any] | None = None) -> Any:
    """GET /aircraft/drones — the fleet's drones. Returns the raw `data` payload."""
    return _get("/aircraft/drones", params=params)


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
