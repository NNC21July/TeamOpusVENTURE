"""Garuda Plex authentication.

OAuth 2.0 Client Credentials flow (per the Developer Programme onboarding):
POST client_id + client_secret to https://identity.garuda.io/token and receive
a JWT bearer token valid for ~72 hours. We cache it in memory and refresh when
it is close to expiry (or on demand after a 401).

Credentials come from .env (GARUDA_CLIENT_ID / GARUDA_CLIENT_SECRET), which is
gitignored. Never log the token or the secret.
"""

from __future__ import annotations

import os
import time
import threading

import httpx
import jwt  # PyJWT
from dotenv import load_dotenv

load_dotenv()

IDENTITY_URL = "https://identity.garuda.io/token"
_REFRESH_SKEW_SECONDS = 60  # refresh a minute before the token actually expires
_FALLBACK_TTL_SECONDS = 72 * 3600  # onboarding states 72h; used only if exp is unreadable

_cache: dict[str, object] = {"token": None, "expires_at": 0.0}
_lock = threading.Lock()


class AuthError(Exception):
    """Raised when a token cannot be obtained."""


def _credentials() -> tuple[str, str]:
    client_id = os.getenv("GARUDA_CLIENT_ID")
    client_secret = os.getenv("GARUDA_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise AuthError(
            "GARUDA_CLIENT_ID / GARUDA_CLIENT_SECRET missing from .env. "
            "Copy .env.example to .env and fill in your developer credentials."
        )
    return client_id, client_secret


def _extract_token(response: httpx.Response) -> str:
    """Pull the JWT out of the token response (JSON access_token, or raw body)."""
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        body = response.json()
        for key in ("access_token", "token", "jwt"):
            if body.get(key):
                return str(body[key])
        raise AuthError(f"token response had no known token field; keys={list(body)}")
    return response.text.strip()


def _expiry_from_jwt(token: str) -> float:
    """Read the JWT's exp claim (authoritative); fall back to 72h from now."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
        if "exp" in claims:
            return float(claims["exp"])
    except Exception:
        pass
    return time.time() + _FALLBACK_TTL_SECONDS


def _fetch_token() -> tuple[str, float]:
    client_id, client_secret = _credentials()
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "resource": "urn:wl:jwt",
    }
    try:
        response = httpx.post(
            IDENTITY_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AuthError(f"token request failed: {exc}") from exc
    token = _extract_token(response)
    return token, _expiry_from_jwt(token)


def get_token(force_refresh: bool = False) -> str:
    """Return a valid bearer token, fetching or refreshing as needed."""
    with _lock:
        now = time.time()
        expired = now >= float(_cache["expires_at"]) - _REFRESH_SKEW_SECONDS
        if force_refresh or _cache["token"] is None or expired:
            token, expires_at = _fetch_token()
            _cache["token"], _cache["expires_at"] = token, expires_at
        return str(_cache["token"])


if __name__ == "__main__":
    import datetime

    tok = get_token()
    exp = float(_cache["expires_at"])
    print("Token acquired.")
    print("  length :", len(tok))
    print("  preview:", tok[:12] + "..." + tok[-6:])
    print("  expires:", datetime.datetime.fromtimestamp(exp).isoformat())
