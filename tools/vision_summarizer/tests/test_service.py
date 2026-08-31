from datetime import datetime, timezone

from tools.vision_summarizer.decision_types import DetectionShape, SummaryStatus
from tools.vision_summarizer.request_response_schemas import MediaItem, RawDetection, SummarizeFlightRequest
from tools.vision_summarizer.service import summarize_flight
from tools.vision_summarizer.tests.fakes import FakeDetectionClient, FakeMediaClient


def make_media(media_id: str, captured_at: datetime, media_type: str = "image") -> MediaItem:
    return MediaItem(media_id=media_id, media_type=media_type, captured_at=captured_at)


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
    # Notes must reflect the real per-item reason, not a hardcoded blanket
    # claim about the cause (e.g. "Geo AI was unreachable") — the actual
    # cause could just as easily be an unsupported media type.
    assert "MEDIA-1" in result.notes[0]
    assert "unreachable" not in result.notes[0].lower()


def test_reference_label_populates_relation_and_is_excluded_from_findings() -> None:
    # reference_label must be supplied by the caller — there's no fixed
    # label taxonomy to guess from (each annotate.garuda.io project defines
    # its own), so this only activates when the caller says which label
    # means "structural reference" for this project.
    request = SummarizeFlightRequest(flight_id="FLIGHT-1", reference_label="facade")
    captured_at = datetime(2026, 8, 1, 9, 14, tzinfo=timezone.utc)
    media_client = FakeMediaClient(media=[make_media("MEDIA-1", captured_at)])

    reference = RawDetection(
        media_id="MEDIA-1", object_label="facade", score=0.99,
        shape=DetectionShape.YOLO_BBOX, bbox=(0.5, 0.5, 1.0, 1.0),
    )
    crack = RawDetection(
        media_id="MEDIA-1", object_label="crack", score=0.9,
        shape=DetectionShape.YOLO_BBOX, bbox=(0.5, 0.5, 0.05, 0.05),
    )
    detection_client = FakeDetectionClient(detections_by_media={"MEDIA-1": [reference, crack]})

    result = summarize_flight(request=request, media_client=media_client, detection_client=detection_client)

    assert result.status is SummaryStatus.COMPLETE
    findings = result.findings[0].detections
    assert all(d.object_label != "facade" for d in findings)  # reference is not a finding
    assert len(findings) == 1
    assert findings[0].object_label == "crack"
    assert findings[0].relation == "overlapping the facade"


def test_no_reference_label_reports_every_detection_as_a_finding() -> None:
    # Without an explicit reference_label, nothing is assumed about the
    # label taxonomy: a detection labeled "facade" is just another finding,
    # not silently treated as a structural reference.
    request = SummarizeFlightRequest(flight_id="FLIGHT-1")
    captured_at = datetime(2026, 8, 1, 9, 14, tzinfo=timezone.utc)
    media_client = FakeMediaClient(media=[make_media("MEDIA-1", captured_at)])

    facade_detection = RawDetection(
        media_id="MEDIA-1", object_label="facade", score=0.99,
        shape=DetectionShape.YOLO_BBOX, bbox=(0.5, 0.5, 1.0, 1.0),
    )
    detection_client = FakeDetectionClient(detections_by_media={"MEDIA-1": [facade_detection]})

    result = summarize_flight(request=request, media_client=media_client, detection_client=detection_client)

    findings = result.findings[0].detections
    assert len(findings) == 1
    assert findings[0].object_label == "facade"
    assert findings[0].relation is None


def test_video_finding_forces_partial_status_with_honest_note() -> None:
    # Even when the detection call itself succeeds for a video (via a
    # single Garuda-selected frame — see GarudaDetectionClient), that's not
    # full video coverage, and the response must say so rather than
    # reporting COMPLETE as if the whole video was reviewed.
    request = SummarizeFlightRequest(flight_id="FLIGHT-1")
    captured_at = datetime(2026, 8, 1, 9, 14, tzinfo=timezone.utc)
    media_client = FakeMediaClient(
        media=[make_media("VIDEO-1", captured_at, media_type="video")]
    )
    detection_client = FakeDetectionClient(
        detections_by_media={"VIDEO-1": [make_detection("VIDEO-1")]}
    )

    result = summarize_flight(request=request, media_client=media_client, detection_client=detection_client)

    assert result.status is SummaryStatus.PARTIAL
    assert len(result.findings) == 1
    assert "VIDEO-1" in result.notes[0]
    assert "single representative frame" in result.notes[0]
