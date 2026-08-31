"""Offline demo — NOT part of the test suite, NOT wired into server.py.

Runs the real summarize_flight pipeline end-to-end against your own
annotation CSV, with zero network calls: FakeMediaClient/FakeDetectionClient
(tests/fakes.py) stand in for GarudaMediaClient/GarudaDetectionClient. Use
this to demo the synthesis step while the live Inspection Ops / Geo AI
services are down, or while Garuda's create_detections labels-format bug is
still unresolved (see rest_client.py's outage/bug notes) — nothing here
depends on either being fixed.

Usage (run from the repo root, as a module so `tools.*` imports resolve):
    python -m tools.vision_summarizer.demo_synthesize_from_csv /path/to/annotations.csv <image-filename> [flight_id]

Example:
    python -m tools.vision_summarizer.demo_synthesize_from_csv labels.csv facade_inspection_test.jpg
"""

import sys
from datetime import datetime, timezone

from tools.vision_summarizer.annotation_import import parse_csv_rows, rows_for_filename, rows_to_raw_detections
from tools.vision_summarizer.request_response_schemas import MediaItem, SummarizeFlightRequest
from tools.vision_summarizer.service import summarize_flight
from tools.vision_summarizer.tests.fakes import FakeDetectionClient, FakeMediaClient


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} /path/to/annotations.csv <image-filename> [flight_id]")
        sys.exit(1)

    csv_path, filename = sys.argv[1], sys.argv[2]
    flight_id = sys.argv[3] if len(sys.argv) > 3 else "DEMO-FLIGHT"

    rows = rows_for_filename(parse_csv_rows(csv_path), filename)
    if not rows:
        sys.exit(f"No rows in {csv_path} match filename {filename!r}")

    media_id = f"DEMO-{filename}"
    detections = rows_to_raw_detections(rows, media_id=media_id)
    print(f"Loaded {len(detections)} annotation(s) for {filename} as fake detections\n")

    media_client = FakeMediaClient(
        media=[MediaItem(media_id=media_id, media_type="image", captured_at=datetime.now(timezone.utc))]
    )
    detection_client = FakeDetectionClient(detections_by_media={media_id: detections})

    result = summarize_flight(
        request=SummarizeFlightRequest(flight_id=flight_id),
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
