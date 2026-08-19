"""Turns raw detection geometry into plain-language position descriptors.

Geo AI's model returns confirmed *what* (an object label) and *where in pixel-
ratio terms* (a bbox or polygon) — but nothing that reads like a description a
pilot or LLM can use directly ("a person near the top-right of the frame").
This module is the rule-based, no-ML layer that closes that gap: pure
geometry, no model call, so it stays cheap and deterministic per the "don't
build CV from scratch" guidance in the tool contract.
"""

from tools.vision_summarizer.decision_types import DetectionShape
from tools.vision_summarizer.request_response_schemas import RawDetection

# 3x3 grid labels, matched to (row, col) from a normalized centroid
_ROW_LABELS = ("upper", "middle", "lower")
_COL_LABELS = ("left", "center", "right")


def centroid_of(detection: RawDetection) -> tuple[float, float]:
    """Return the (x, y) centroid of a detection in [0,1] frame-ratio terms."""
    if detection.shape is DetectionShape.YOLO_BBOX and detection.bbox is not None:
        x, y, _w, _h = detection.bbox
        return (x, y)

    if detection.shape is DetectionShape.YOLO_POLY and detection.polygon:
        xs = [point[0] for point in detection.polygon]
        ys = [point[1] for point in detection.polygon]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    # Missing/invalid geometry — treat as dead center rather than crashing;
    # the caller can still report the detection, just without a precise position.
    return (0.5, 0.5)


def describe_position(detection: RawDetection) -> str:
    """Convert a detection's geometry into a 3x3-grid plain-language position.

    e.g. (0.85, 0.1) -> "upper-right"; (0.5, 0.5) -> "center".
    """
    x, y = centroid_of(detection)
    x = min(max(x, 0.0), 1.0)
    y = min(max(y, 0.0), 1.0)

    row = _ROW_LABELS[min(int(y * 3), 2)]
    col = _COL_LABELS[min(int(x * 3), 2)]

    if row == "middle" and col == "center":
        return "center"
    if col == "center":
        return row
    if row == "middle":
        return col
    return f"{row}-{col}"


def describe_relation(
    detection: RawDetection,
    reference: RawDetection | None,
    *,
    overlap_threshold: float = 0.0,
) -> str | None:
    """Optionally describe a detection relative to a reference object's box
    (e.g. the facade/structure itself, if Geo AI's model also detects it).

    Returns None if there's no reference to compare against — callers should
    fall back to `describe_position` alone in that case. This only handles
    bbox-vs-bbox axis-aligned overlap; polygon-vs-polygon relation is out of
    scope for now.
    """
    if reference is None:
        return None
    if detection.shape is not DetectionShape.YOLO_BBOX or detection.bbox is None:
        return None
    if reference.shape is not DetectionShape.YOLO_BBOX or reference.bbox is None:
        return None

    dx, dy, dw, dh = detection.bbox
    rx, ry, rw, rh = reference.bbox

    d_left, d_right = dx - dw / 2, dx + dw / 2
    d_top, d_bottom = dy - dh / 2, dy + dh / 2
    r_left, r_right = rx - rw / 2, rx + rw / 2
    r_top, r_bottom = ry - rh / 2, ry + rh / 2

    overlap_x = max(0.0, min(d_right, r_right) - max(d_left, r_left))
    overlap_y = max(0.0, min(d_bottom, r_bottom) - max(d_top, r_top))
    overlap_area = overlap_x * overlap_y

    if overlap_area > overlap_threshold:
        return f"overlapping the {reference.object_label}"

    # Close but not overlapping — simple centroid-distance based "near" check
    distance = ((dx - rx) ** 2 + (dy - ry) ** 2) ** 0.5
    if distance < 0.15:
        return f"near the {reference.object_label}"

    return None
