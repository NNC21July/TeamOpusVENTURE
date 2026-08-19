from tools.vision_summarizer.decision_types import DetectionShape
from tools.vision_summarizer.descriptors.dedup import dedupe_detections
from tools.vision_summarizer.request_response_schemas import RawDetection


def make_detection(
    *, x: float, y: float, score: float = 0.9, label: str = "person",
    frame_time_s: float | None = None, track_id: str | None = None,
) -> RawDetection:
    return RawDetection(
        media_id="MEDIA-1",
        object_label=label,
        score=score,
        shape=DetectionShape.YOLO_BBOX,
        bbox=(x, y, 0.1, 0.1),
        frame_time_s=frame_time_s,
        track_id=track_id,
    )


def test_empty_input_returns_empty_output() -> None:
    assert dedupe_detections([]) == []


def test_groups_by_track_id_when_available() -> None:
    detections = [
        make_detection(x=0.1, y=0.1, frame_time_s=0.0, track_id="obj-1"),
        make_detection(x=0.15, y=0.1, frame_time_s=1.0, track_id="obj-1"),
        make_detection(x=0.9, y=0.9, frame_time_s=1.0, track_id="obj-2", label="crack"),
    ]
    result = dedupe_detections(detections)
    assert len(result) == 2
    labels = {d.object_label for d in result}
    assert labels == {"person", "crack"}
    person_entry = next(d for d in result if d.object_label == "person")
    assert person_entry.occurrence_count == 2


def test_groups_by_proximity_when_no_track_id() -> None:
    detections = [
        make_detection(x=0.50, y=0.50, frame_time_s=0.0),
        make_detection(x=0.52, y=0.50, frame_time_s=0.5),
        make_detection(x=0.53, y=0.51, frame_time_s=1.0),
    ]
    result = dedupe_detections(detections)
    assert len(result) == 1
    assert result[0].occurrence_count == 3
    assert result[0].first_seen_s == 0.0
    assert result[0].last_seen_s == 1.0


def test_large_spatial_jump_creates_separate_cluster() -> None:
    detections = [
        make_detection(x=0.1, y=0.1, frame_time_s=0.0),
        make_detection(x=0.9, y=0.9, frame_time_s=0.5),
    ]
    result = dedupe_detections(detections)
    assert len(result) == 2


def test_large_time_gap_creates_separate_cluster() -> None:
    detections = [
        make_detection(x=0.5, y=0.5, frame_time_s=0.0),
        make_detection(x=0.5, y=0.5, frame_time_s=10.0),
    ]
    result = dedupe_detections(detections)
    assert len(result) == 2


def test_different_labels_never_merge_even_if_close() -> None:
    detections = [
        make_detection(x=0.5, y=0.5, frame_time_s=0.0, label="person"),
        make_detection(x=0.5, y=0.5, frame_time_s=0.1, label="crack"),
    ]
    result = dedupe_detections(detections)
    assert len(result) == 2


def test_represents_cluster_with_highest_confidence_detection() -> None:
    detections = [
        make_detection(x=0.5, y=0.5, frame_time_s=0.0, score=0.4),
        make_detection(x=0.5, y=0.5, frame_time_s=0.5, score=0.95),
    ]
    result = dedupe_detections(detections)
    assert len(result) == 1
    assert result[0].score == 0.95


def test_relation_is_applied_per_cluster_when_reference_given() -> None:
    reference = make_detection(x=0.5, y=0.5, label="facade")
    detections = [
        make_detection(x=0.5, y=0.5, frame_time_s=0.0, label="person"),
        make_detection(x=0.51, y=0.5, frame_time_s=0.5, label="person"),
    ]
    result = dedupe_detections(detections, reference=reference)
    assert len(result) == 1
    assert result[0].relation == "overlapping the facade"
