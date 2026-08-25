"""Concrete MediaClient implementation, backed by api_client/rest_client.py.

Kept separate from client_protocol.py (which only defines the interface) so
the service layer / tests never need to import the REST client or httpx
directly — matches the encapsulation pattern rest_client.py documents.
"""

from api_client import rest_client
from tools.vision_summarizer.client_protocol import MediaDataUnavailableError
from tools.vision_summarizer.request_response_schemas import MediaItem


class GarudaMediaClient:
    def get_media_for_flight(self, *, flight_id: str) -> list[MediaItem]:
        # CONFIRMED (Inspection Ops Service Swagger): there is no direct
        # flight -> media link anywhere in the Media Service. The real chain
        # is Inspection.flight_ids[] -> that inspection's images -> each
        # image's media_id. See rest_client.get_inspections/get_inspection_images.
        try:
            inspections_data = rest_client.get_inspections()
        except rest_client.APIError as exc:
            raise MediaDataUnavailableError(str(exc)) from exc

        inspection_ids = [
            inspection["inspection_id"]
            for inspection in _extract_inspection_list(inspections_data)
            if flight_id in (inspection.get("flight_ids") or [])
        ]
        if not inspection_ids:
            return []

        media_items: list[MediaItem] = []
        for inspection_id in inspection_ids:
            try:
                images_data = rest_client.get_inspection_images(
                    params={"inspection_id": inspection_id}
                )
            except rest_client.APIError as exc:
                raise MediaDataUnavailableError(str(exc)) from exc

            for image in _extract_image_list(images_data):
                media_id = image.get("media_id")
                if media_id:
                    # inspection_image records don't carry exif/timestamp —
                    # that lives on the underlying Media object. Skipped for
                    # now (captured_at is only used for best-effort sorting,
                    # which already falls back gracefully); could be
                    # enriched later via a get_media_by_id call per item if
                    # actually needed.
                    media_items.append(MediaItem(media_id=media_id, media_type="image"))
        return media_items


def _extract_inspection_list(data: object) -> list[dict]:
    if isinstance(data, dict):
        return data.get("inspections", data.get("results", []))
    if isinstance(data, list):
        return data
    return []


def _extract_image_list(data: object) -> list[dict]:
    if isinstance(data, dict):
        return data.get("images", data.get("results", []))
    if isinstance(data, list):
        return data
    return []


