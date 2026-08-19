from datetime import datetime, timezone

from tools.vision_summarizer.decision_types import DetectionShape, SummaryStatus
from tools.vision_summarizer.request_response_schemas import MediaItem, RawDetection, SummarizeFlightRequest
from tools.vision_summarizer.service import summarize_flight
from tools.vision_summarizer.tests.fakes import FakeDetectionClient, FakeMediaClient


def make_media(media_id: str, captured_at: datetime) -> MediaItem:
    return MediaItem(media_id=media_id, media_type="image", captured_at=captured_at)


def make_detection(media_id: str, label: str = "crack") -> RawDetection:
    return RawDetection(
        media_id=media_id, object_label=label, score=0.9,
        shape=DetectionShape.YOLO_BBOX, bbox=(0.8, 0.1, 0.1, 0.1),
    )


def test_invalid_flight_id_returns_needs_info_without_calling_clients() -> None:
    request = SummarizeFlightRequest(flight_id="")
    media_client = FakeMediaClient()
    detection_client = FakeDetectionClient()

    result = summarize_flight(request=request, media_client=media_client, detection_client=detection_client)

    assert result.status is SummaryStatus.NEEDS_INFO
    assert media_client.requested_flight_ids == []


def test_media_service_unavailable_returns_unknown() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1")
    media_client = FakeMediaClient(unavailable=True)
    detection_client = FakeDetectionClient()

    result = summarize_flight(request=request, media_client=media_client, detection_client=detection_client)

    assert result.status is SummaryStatus.UNKNOWN


def test_no_media_returns_no_media_status() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1")
    media_client = FakeMediaClient(media=[])
    detection_client = FakeDetectionClient()

    result = summarize_flight(request=request, media_client=media_client, detection_client=detection_client)

    assert result.status is SummaryStatus.NO_MEDIA


def test_complete_flow_returns_complete_status_with_findings() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1")
    captured_at = datetime(2026, 8, 1, 9, 14, tzinfo=timezone.utc)
    media_client = FakeMediaClient(media=[make_media("MEDIA-1", captured_at)])
    detection_client = FakeDetectionClient(detections_by_media={"MEDIA-1": [make_detection("MEDIA-1")]})

    result = summarize_flight(request=request, media_client=media_client, detection_client=detection_client)

    assert result.status is SummaryStatus.COMPLETE
    assert result.media_count == 1
    assert len(result.findings) == 1
    assert result.findings[0].detections[0].object_label == "crack"
    # No LLM/prose call inside the tool — by design (see service.py docstring)
    assert not hasattr(result, "summary")


def test_partial_detection_failure_returns_partial_status() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1")
    captured_at = datetime(2026, 8, 1, 9, 14, tzinfo=timezone.utc)
    media_client = FakeMediaClient(
        media=[make_media("MEDIA-1", captured_at), make_media("MEDIA-2", captured_at)]
    )
    detection_client = FakeDetectionClient(
        detections_by_media={"MEDIA-1": [make_detection("MEDIA-1")]},
        unavailable_media_ids={"MEDIA-2"},
    )

    result = summarize_flight(request=request, media_client=media_client, detection_client=detection_client)

    assert result.status is SummaryStatus.PARTIAL
    assert "MEDIA-2" in result.notes[0]


def test_all_detections_unavailable_returns_unknown() -> None:
    request = SummarizeFlightRequest(flight_id="FLIGHT-1")
    captured_at = datetime(2026, 8, 1, 9, 14, tzinfo=timezone.utc)
    media_client = FakeMediaClient(media=[make_media("MEDIA-1", captured_at)])
    detection_client = FakeDetectionClient(unavailable_media_ids={"MEDIA-1"})

    result = summarize_flight(request=request, media_client=media_client, detection_client=detection_client)

    assert result.status is SummaryStatus.UNKNOWN
