from tools.vision_summarizer.client_protocol import DetectionDataUnavailableError, MediaDataUnavailableError
from tools.vision_summarizer.request_response_schemas import MediaItem, RawDetection


class FakeMediaClient:
    def __init__(self, media: list[MediaItem] | None = None, *, unavailable: bool = False) -> None:
        self._media = list(media) if media is not None else []
        self._unavailable = unavailable
        self.requested_flight_ids: list[str] = []

    def get_media_for_flight(self, *, flight_id: str) -> list[MediaItem]:
        self.requested_flight_ids.append(flight_id)
        if self._unavailable:
            raise MediaDataUnavailableError("Fake media data is unavailable")
        return list(self._media)


class FakeDetectionClient:
    def __init__(
        self,
        detections_by_media: dict[str, list[RawDetection]] | None = None,
        *,
        unavailable_media_ids: set[str] | None = None,
    ) -> None:
        self._detections_by_media = detections_by_media or {}
        self._unavailable_media_ids = unavailable_media_ids or set()
        self.requested_media_ids: list[str] = []

    def get_detections_for_media(self, *, media: MediaItem) -> list[RawDetection]:
        self.requested_media_ids.append(media.media_id)
        if media.media_id in self._unavailable_media_ids:
            raise DetectionDataUnavailableError(f"Fake detection data unavailable for {media.media_id}")
        return list(self._detections_by_media.get(media.media_id, []))
