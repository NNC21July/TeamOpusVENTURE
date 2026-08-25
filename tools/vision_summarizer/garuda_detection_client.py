"""Concrete DetectionClient implementation, backed by api_client/rest_client.py.

/ml_detections/upload takes a raw image, not a media_id reference — so this
first downloads the media's bytes (via its Media Asset Service URL), then
uploads them to Geo AI. See Research 2, "Resolved: upload takes raw image".

Video support: Geo AI only accepts still image freeze frames (confirmed in
its own Swagger docs), and full video frame-sampling is deliberately out of
scope for now (see team discussion — real frame extraction needs a new local
dependency and is bigger, separate work). But the Media Service's own
size-variant endpoints already return "a single frame from the video" for
video-type media (confirmed in its docs) — so video is handled here by
reusing that single Garuda-selected frame exactly like an image. This is a
partial-coverage snapshot, not a full video review; service.py is
responsible for surfacing that distinction to the caller (forcing PARTIAL
status + an explicit note), since this client has no way to know how
complete a summary its caller intends to build from the result.
"""

from tools.vision_summarizer.decision_types import DetectionShape

from api_client import rest_client
from tools.vision_summarizer.client_protocol import DetectionDataUnavailableError
from tools.vision_summarizer.request_response_schemas import MediaItem, RawDetection

# Which labels to request detection for. Placeholder until Garuda confirms
# the label taxonomy for facade inspection specifically (see Research 2,
# "Still to Research").
_DEFAULT_LABELS = ["defect", "crack", "spalling", "stain", "person"]

# Identifies who/what triggered detection, per /ml_detections/upload's
# required `created_by` field. Using a fixed tool identity for now — revisit
# if Garuda expects a specific model-version id here instead.
_CREATED_BY = "vision-summarizer-tool"

# "video" is handled via a single Garuda-selected representative frame (see
# module docstring) — not full video coverage, but not rejected outright.
_SUPPORTED_MEDIA_TYPES = ("image", "video")


class GarudaDetectionClient:
    def get_detections_for_media(self, *, media: MediaItem) -> list[RawDetection]:
        if media.media_type not in _SUPPORTED_MEDIA_TYPES:
            raise DetectionDataUnavailableError(
                f"media_type '{media.media_type}' is not supported "
                f"(supported: {', '.join(_SUPPORTED_MEDIA_TYPES)})"
            )

        try:
            image_bytes = rest_client.get_media_bytes(media.media_id, variant="fullscreen")
            data = rest_client.create_detections(
                image_bytes=image_bytes,
                filename=f"{media.media_id}.jpg",
                labels=_DEFAULT_LABELS,
                created_by=_CREATED_BY,
            )
        except rest_client.APIError as exc:
            raise DetectionDataUnavailableError(str(exc)) from exc

        raw_detections = _extract_detection_list(data)
        return [_to_raw_detection(item, media.media_id) for item in raw_detections if isinstance(item, dict)]


def _extract_detection_list(data: object) -> list[dict]:
    if isinstance(data, dict):
        return data.get("ml_detections", [])
    if isinstance(data, list):
        return data
    return []


def _to_raw_detection(raw: dict, fallback_media_id: str) -> RawDetection:
    label = raw.get("label", {})
    shape_value = label.get("shape")
    try:
        shape = DetectionShape(shape_value)
    except ValueError:
        shape = DetectionShape.YOLO_BBOX  # safe default; bbox will be None below if absent

    bbox = tuple(label["bbox"]) if isinstance(label.get("bbox"), list) else None
    polygon = (
        tuple(tuple(point) for point in label["polygon"])
        if isinstance(label.get("polygon"), list)
        else None
    )

    return RawDetection(
        media_id=raw.get("media_id", fallback_media_id),
        object_label=label.get("object", "unknown"),
        score=float(label.get("score", 0.0)),
        shape=shape,
        bbox=bbox,
        polygon=polygon,
        # NOTE: Geo AI's documented MLDetection schema doesn't show a
        # track_id or frame_time_s field — both are still unconfirmed with
        # Garuda (see Research 2, "Still to Research"). Left as None until
        # confirmed; dedup.py already handles the no-track_id case.
        frame_time_s=None,
        track_id=raw.get("track_id"),
    )
