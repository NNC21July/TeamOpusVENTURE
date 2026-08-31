"""Converts human-annotated bounding boxes — from either a bbox CSV or a YOLO
.txt export — into Geo AI's MLDetection.label format (ready for
rest_client.create_detections()) or straight into RawDetection objects for
offline use.

CSV format (no header row): label, x, y, w, h, filename, image_width, image_height
— x/y is the TOP-LEFT corner in pixels (confirmed against real data: some rows
only make sense that way). RawDetection.bbox is CENTER-based ratios, matching
YOLO's own convention, so _to_center_ratio_bbox does the pixel + corner->center
conversion for this format.

YOLO format (one .txt per image, one detection per line): class_id x_center
y_center width height — already normalized [0,1] and center-based, i.e.
already RawDetection.bbox's own shape. No conversion needed; class_id ->
label name has to come from the caller (class_names), since a .txt file
alone carries no label names.

NOTE: sending either format's Geo AI wire payload is what currently fails
against the live service with Garuda's Mongoose "ObjectExpectedError" (see
rest_client.create_detections's docstring) — these functions produce the
format Garuda's own docs specify; not yet confirmed to work end-to-end.
"""

import csv
import json
from dataclasses import dataclass

from tools.vision_summarizer.decision_types import DetectionShape
from tools.vision_summarizer.request_response_schemas import RawDetection


@dataclass(frozen=True)
class AnnotationRow:
    label: str
    x: float
    y: float
    w: float
    h: float
    filename: str
    image_width: float
    image_height: float


def parse_csv_rows(csv_path: str) -> list[AnnotationRow]:
    rows = []
    with open(csv_path, newline="") as f:
        for label, x, y, w, h, filename, image_width, image_height in csv.reader(f):
            rows.append(
                AnnotationRow(
                    label=label,
                    x=float(x),
                    y=float(y),
                    w=float(w),
                    h=float(h),
                    filename=filename,
                    image_width=float(image_width),
                    image_height=float(image_height),
                )
            )
    return rows


def rows_for_filename(rows: list[AnnotationRow], filename: str) -> list[AnnotationRow]:
    return [row for row in rows if row.filename == filename]


def _to_center_ratio_bbox(row: AnnotationRow) -> tuple[float, float, float, float]:
    """Convert a CSV row's pixel bbox — (x, y) is the TOP-LEFT corner in this
    CSV format — into the CENTER-based ratio bbox the rest of the pipeline
    expects. RawDetection.bbox is (center_x, center_y, w, h) as fractions of
    image size, matching YOLO's own convention (descriptors/spatial.py's
    centroid_of() reads bbox[0:2] directly as a centroid, and
    describe_relation()'s overlap math assumes center +/- half-width) — so
    top-left coordinates must be shifted by half the box size, not just
    divided by image size.
    """
    return (
        (row.x + row.w / 2) / row.image_width,
        (row.y + row.h / 2) / row.image_height,
        row.w / row.image_width,
        row.h / row.image_height,
    )


def rows_to_label_payloads(rows: list[AnnotationRow], *, score: float = 1.0) -> list[str]:
    """Convert annotation rows (one image's worth) into Geo AI's documented
    label format: a JSON array of JSON-stringified label objects.

    score defaults to 1.0 — these are human-verified ground truth, not a
    model confidence, but Geo AI's schema requires the field regardless.
    """
    payloads = []
    for row in rows:
        label_obj = {
            "shape": "yolo-bbox",
            "bbox": list(_to_center_ratio_bbox(row)),
            "object": row.label,
            "score": score,
        }
        payloads.append(json.dumps(label_obj))
    return payloads


def rows_to_raw_detections(rows: list[AnnotationRow], *, media_id: str, score: float = 1.0) -> list[RawDetection]:
    """Convert annotation rows straight into RawDetection objects — the
    in-memory shape summarize_flight actually consumes — skipping the Geo AI
    wire format entirely. For demos/fakes where nothing goes over the
    network; see demo_synthesize_from_csv.py.
    """
    return [
        RawDetection(
            media_id=media_id,
            object_label=row.label,
            score=score,
            shape=DetectionShape.YOLO_BBOX,
            bbox=_to_center_ratio_bbox(row),
        )
        for row in rows
    ]


@dataclass(frozen=True)
class YoloRow:
    # One line of a YOLO-format .txt annotation file:
    # class_id x_center y_center width height — all already normalized
    # [0,1] and center-based, i.e. exactly RawDetection.bbox's own format.
    # No pixel/top-left conversion needed, unlike the CSV path above.
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float


def parse_yolo_file(txt_path: str) -> list[YoloRow]:
    """Parse one YOLO-format .txt annotation file (one file per image, one
    detection per line). Ignores blank lines; takes only the first 5
    whitespace-separated fields per line, so a trailing confidence column
    (some exporters add one) is tolerated but not used.
    """
    rows = []
    with open(txt_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            class_id, x_center, y_center, width, height = line.split()[:5]
            rows.append(
                YoloRow(
                    class_id=int(class_id),
                    x_center=float(x_center),
                    y_center=float(y_center),
                    width=float(width),
                    height=float(height),
                )
            )
    return rows


def yolo_rows_to_label_payloads(
    rows: list[YoloRow], *, class_names: dict[int, str], score: float = 1.0
) -> list[str]:
    """Convert YOLO rows into Geo AI's documented label format — same output
    shape as rows_to_label_payloads, for the same eventual create_detections
    call. class_names maps each file's class_id to a label string; there is
    no way to infer this from the .txt file alone (it has no names in it),
    so it must be supplied explicitly — never guessed.
    """
    payloads = []
    for row in rows:
        label_obj = {
            "shape": "yolo-bbox",
            "bbox": [row.x_center, row.y_center, row.width, row.height],
            "object": class_names[row.class_id],
            "score": score,
        }
        payloads.append(json.dumps(label_obj))
    return payloads


def yolo_rows_to_raw_detections(
    rows: list[YoloRow], *, media_id: str, class_names: dict[int, str], score: float = 1.0
) -> list[RawDetection]:
    """YOLO-row equivalent of rows_to_raw_detections — see its docstring."""
    return [
        RawDetection(
            media_id=media_id,
            object_label=class_names[row.class_id],
            score=score,
            shape=DetectionShape.YOLO_BBOX,
            bbox=(row.x_center, row.y_center, row.width, row.height),
        )
        for row in rows
    ]
