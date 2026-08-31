"""Offline demo — NOT part of the test suite, NOT wired into server.py.

YOLO-format equivalent of demo_synthesize_from_csv.py: runs the real
summarize_flight pipeline end-to-end against a YOLO .txt annotation file,
with zero network calls. See that file's docstring for why this exists.

A YOLO .txt file has no label names in it (just class_id x_center y_center
width height per line) — class_names must be supplied on the command line,
ordered by class_id, e.g. "crack,spalling" means class 0 -> crack,
class 1 -> spalling. There is nothing to infer this from; get it from
whatever classes.txt/data.yaml your annotate.garuda.io export paired with
this .txt file, and confirm the order before trusting the output.

Usage (run from the repo root, as a module so `tools.*` imports resolve):
    python -m tools.vision_summarizer.demo_synthesize_from_yolo /path/to/annotations.txt <class_names> [flight_id] [reference_label]

Example:
    python -m tools.vision_summarizer.demo_synthesize_from_yolo facade_inspection_test.txt "crack,spalling"
"""

import sys
from datetime import datetime, timezone

from tools.vision_summarizer.annotation_import import parse_yolo_file, yolo_rows_to_raw_detections
from tools.vision_summarizer.request_response_schemas import MediaItem, SummarizeFlightRequest
from tools.vision_summarizer.service import summarize_flight
from tools.vision_summarizer.tests.fakes import FakeDetectionClient, FakeMediaClient


def main() -> None:
    if len(sys.argv) < 3:
        print(
            f"Usage: python {sys.argv[0]} /path/to/annotations.txt <class_names> [flight_id] [reference_label]\n"
            f'  class_names: comma-separated, ordered by class_id, e.g. "crack,spalling"'
        )
        sys.exit(1)

    txt_path, class_names_arg = sys.argv[1], sys.argv[2]
    flight_id = sys.argv[3] if len(sys.argv) > 3 else "DEMO-FLIGHT"
    reference_label = sys.argv[4] if len(sys.argv) > 4 else None

    class_names = {i: name.strip() for i, name in enumerate(class_names_arg.split(","))}
    print(f"Using class mapping: {class_names}")

    rows = parse_yolo_file(txt_path)
    if not rows:
        sys.exit(f"No rows parsed from {txt_path}")

    unknown_ids = {row.class_id for row in rows} - set(class_names)
    if unknown_ids:
        sys.exit(f"class_names has no entry for class_id(s) {sorted(unknown_ids)} found in {txt_path}")

    filename = txt_path.rsplit("/", 1)[-1]
    media_id = f"DEMO-{filename}"
    detections = yolo_rows_to_raw_detections(rows, media_id=media_id, class_names=class_names)
    print(f"Loaded {len(detections)} annotation(s) from {filename} as fake detections\n")

    media_client = FakeMediaClient(
        media=[MediaItem(media_id=media_id, media_type="image", captured_at=datetime.now(timezone.utc))]
    )
    detection_client = FakeDetectionClient(detections_by_media={media_id: detections})

    result = summarize_flight(
        request=SummarizeFlightRequest(flight_id=flight_id, reference_label=reference_label),
        media_client=media_client,
        detection_client=detection_client,
    )

    print(f"status: {result.status.value}")
    print(f"media_count: {result.media_count}")
    for finding in result.findings:
        print(f"\nmedia_id={finding.media_id}")
        for d in finding.detections:
            where = f"{d.position}, {d.relation}" if d.relation else d.position
            print(f"  - {d.object_label} x{d.occurrence_count} at {where}, score={d.score}")
    if result.notes:
        print("\nnotes:")
        for note in result.notes:
            print(f"  - {note}")


if __name__ == "__main__":
    main()
