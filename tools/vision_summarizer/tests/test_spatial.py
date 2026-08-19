from tools.vision_summarizer.decision_types import DetectionShape
from tools.vision_summarizer.descriptors.spatial import describe_position, describe_relation
from tools.vision_summarizer.request_response_schemas import RawDetection


def make_bbox_detection(x: float, y: float, w: float = 0.1, h: float = 0.1, label: str = "crack") -> RawDetection:
    return RawDetection(
        media_id="MEDIA-1",
        object_label=label,
        score=0.9,
        shape=DetectionShape.YOLO_BBOX,
        bbox=(x, y, w, h),
    )


def test_center_position() -> None:
    detection = make_bbox_detection(0.5, 0.5)
    assert describe_position(detection) == "center"


def test_upper_right_position() -> None:
    detection = make_bbox_detection(0.9, 0.05)
    assert describe_position(detection) == "upper-right"


def test_lower_left_position() -> None:
    detection = make_bbox_detection(0.05, 0.95)
    assert describe_position(detection) == "lower-left"


def test_edge_column_only_uses_row_label() -> None:
    detection = make_bbox_detection(0.5, 0.05)
    assert describe_position(detection) == "upper"


def test_polygon_uses_centroid_average() -> None:
    detection = RawDetection(
        media_id="MEDIA-1",
        object_label="crack",
        score=0.9,
        shape=DetectionShape.YOLO_POLY,
        polygon=((0.8, 0.8), (0.9, 0.9), (0.9, 0.8)),
    )
    assert describe_position(detection) == "lower-right"


def test_position_is_clamped_for_out_of_range_values() -> None:
    detection = make_bbox_detection(1.5, -0.5)
    assert describe_position(detection) == "upper-right"


def test_relation_returns_none_without_reference() -> None:
    detection = make_bbox_detection(0.5, 0.5)
    assert describe_relation(detection, None) is None


def test_relation_detects_overlap_with_reference() -> None:
    detection = make_bbox_detection(0.5, 0.5, w=0.2, h=0.2, label="person")
    reference = make_bbox_detection(0.5, 0.5, w=0.6, h=0.6, label="facade")
    assert describe_relation(detection, reference) == "overlapping the facade"


def test_relation_detects_near_without_overlap() -> None:
    detection = make_bbox_detection(0.5, 0.5, w=0.05, h=0.05, label="person")
    reference = make_bbox_detection(0.58, 0.58, w=0.05, h=0.05, label="facade")
    assert describe_relation(detection, reference) == "near the facade"


def test_relation_returns_none_when_far_from_reference() -> None:
    detection = make_bbox_detection(0.1, 0.1, w=0.05, h=0.05, label="person")
    reference = make_bbox_detection(0.9, 0.9, w=0.05, h=0.05, label="facade")
    assert describe_relation(detection, reference) is None
