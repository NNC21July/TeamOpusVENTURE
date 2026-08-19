"""Concrete DetectionClient implementation, backed by api_client.py.

/ml_detections/upload takes a raw image, not a media_id reference — so this
first downloads the media's bytes (via its Media Asset Service URL), then
uploads them to Geo AI. See Research 2, "Resolved: upload takes raw image".
"""

from tools.vision_summarizer.decision_types import DetectionShape

import api_client
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


class GarudaDetectionClient:
    def get_detections_for_media(self, *, media: MediaItem) -> list[RawDetection]:
        if media.media_type != "image":
            # Confirmed in Research 2: Geo AI only supports still image
            # freeze frames. Video needs frame extraction before this call,
            # which isn't implemented yet — surface as unavailable rather
            # than silently skipping or crashing.
            raise DetectionDataUnavailableError(
                f"media_type '{media.media_type}' is not yet supported "
                "(only 'image' is handled — video needs frame-sampling first)"
            )

        if not media.url:
            raise DetectionDataUnavailableError(f"no fetchable URL for media {media.media_id}")

        try:
            image_bytes = api_client.get_media_bytes(media.url)
            data = api_client.create_detections(
                image_bytes=image_bytes,
                filename=f"{media.media_id}.jpg",
                labels=_DEFAULT_LABELS,
                created_by=_CREATED_BY,
            )
        except api_client.APIError as exc:
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
