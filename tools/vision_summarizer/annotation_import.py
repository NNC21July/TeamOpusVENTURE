"""Converts a human-annotated bounding-box CSV into Geo AI's MLDetection.label
format, ready to pass as the `labels` argument to rest_client.create_detections().

CSV format (no header row): label, x, y, w, h, filename, image_width, image_height
— x/y/w/h are pixel values (a common bbox-export shape). Geo AI's label.bbox is
documented as ratios (see request_response_schemas.RawDetection), so the
pixel -> ratio conversion happens here.

NOTE: sending this exact documented format is what currently fails against the
live service with Garuda's Mongoose "ObjectExpectedError" (see
rest_client.create_detections's docstring) — this module produces the format
Garuda's own docs specify; it is not yet confirmed to work end-to-end.
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
            "bbox": [
                row.x / row.image_width,
                row.y / row.image_height,
                row.w / row.image_width,
                row.h / row.image_height,
            ],
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
            bbox=(
                row.x / row.image_width,
                row.y / row.image_height,
                row.w / row.image_width,
                row.h / row.image_height,
            ),
        )
        for row in rows
    ]
