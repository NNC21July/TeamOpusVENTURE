"""Concrete MediaClient implementation, backed by api_client.py.

Kept separate from client_protocol.py (which only defines the interface) so
the service layer / tests never need to import api_client or httpx directly —
matches the encapsulation pattern api_client.py itself documents.
"""

from datetime import datetime

import api_client
from tools.vision_summarizer.client_protocol import MediaDataUnavailableError
from tools.vision_summarizer.request_response_schemas import MediaItem


class GarudaMediaClient:
    def get_media_for_flight(self, *, flight_id: str) -> list[MediaItem]:
        try:
            data = api_client.get_media_for_flight(flight_id)
        except api_client.APIError as exc:
            raise MediaDataUnavailableError(str(exc)) from exc

        raw_items = _extract_media_list(data)
        return [_to_media_item(item) for item in raw_items if isinstance(item, dict)]


def _extract_media_list(data: object) -> list[dict]:
    if isinstance(data, dict):
        return data.get("media", data.get("results", []))
    if isinstance(data, list):
        return data
    return []


def _to_media_item(raw: dict) -> MediaItem:
    # NOTE: `properties`/`exif` field contents are still being expanded per
    # Research 2 — this reads defensively (.get with fallback) so a missing
    # or differently-shaped field doesn't crash the whole flight summary.
    properties = raw.get("properties") or {}
    exif = properties.get("exif") or raw.get("exif") or {}

    url = _pick_variant_url(properties)
    captured_at = _parse_timestamp(exif.get("timestamp"))
    gps = _parse_gps(exif.get("gps"))

    return MediaItem(
        media_id=raw.get("media_id", ""),
        media_type=raw.get("media_type", "unknown"),
        url=url,
        captured_at=captured_at,
        gps=gps,
    )


def _pick_variant_url(properties: dict) -> str | None:
    # Prefer the highest-resolution variant available for vision input, per
    # Research 2 ("want large/fullscreen/original" over thumb/preview/medium).
    for variant in ("original", "fullscreen", "large"):
        variant_info = properties.get(variant)
        if isinstance(variant_info, dict) and variant_info.get("url"):
            return variant_info["url"]
    return None


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_gps(value: object) -> tuple[float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return (float(value[0]), float(value[1]))
        except (TypeError, ValueError):
            return None
    return None
