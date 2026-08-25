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
    # Takes the whole MediaItem (not just its id) because implementations need
    # both media_id (to fetch raw bytes before uploading — Geo AI takes a raw
    # image, not a media_id reference) and media_type (to decide whether/how
    # a given item can be processed, e.g. image vs. video).
    def get_detections_for_media(self, *, media: MediaItem) -> list[RawDetection]:
        ...
