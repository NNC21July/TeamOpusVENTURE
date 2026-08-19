from enum import Enum


class SummaryStatus(str, Enum):
    # Overall result returned by the vision summarization tool.
    # Always tries to return *something* useful rather than a strict
    # pass/fail, but must flag data quality issues explicitly rather than
    # silently presenting a partial picture as complete.
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NO_MEDIA = "NO_MEDIA"
    NEEDS_INFO = "NEEDS_INFO"
    UNKNOWN = "UNKNOWN"


class DetectionShape(str, Enum):
    # Mirrors Geo AI's MLDetection.label.shape values. Only one of
    # bbox / polygon is populated on a given detection depending on this.
    YOLO_BBOX = "yolo-bbox"
    YOLO_POLY = "yolo-poly"
