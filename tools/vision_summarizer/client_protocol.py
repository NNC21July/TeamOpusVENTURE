from typing import Protocol

from tools.vision_summarizer.request_response_schemas import MediaItem, RawDetection


class MediaDataUnavailableError(RuntimeError):
    """Raised when a flight's media cannot be retrieved from Media Asset Service."""


class DetectionDataUnavailableError(RuntimeError):
    """Raised when detections cannot be retrieved/created via Geo AI Config Service."""


class MediaClient(Protocol):
    # Capability required from the API Client for the Media Asset Service side
    def get_media_for_flight(self, *, flight_id: str) -> list[MediaItem]:
        ...


class DetectionClient(Protocol):
    # Capability required from the API Client for the Geo AI Config Service side.
    # Takes the whole MediaItem (not just its id) because implementations that
    # trigger fresh detection (POST /ml_detections/upload) need the media's
    # URL to download the raw image bytes before uploading them — Geo AI
    # takes a raw image, not a media_id reference (see Research 2).
    def get_detections_for_media(self, *, media: MediaItem) -> list[RawDetection]:
        ...
