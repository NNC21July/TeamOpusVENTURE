"""Manual dev script — NOT part of the test suite.

Uploads an inspection image and persists its pre-computed annotations (from a
bbox CSV export, e.g. labels_my-project-name_*.csv) as Geo AI detections
against it. See annotation_import.py for the CSV -> label conversion, and
rest_client.create_detections's docstring for the currently-open blocker on
Garuda's side (this script's step 2 is expected to fail until that's fixed).

Usage:
    python tools/vision_summarizer/import_annotations.py /path/to/image.jpg /path/to/annotations.csv [inspection_id] [elevation_id]

inspection_id/elevation_id default to reusing the VisSumTest facility's
objects, created by create_test_inspection_data.py.
"""

import sys

from api_client import rest_client
from tools.vision_summarizer.annotation_import import (
    parse_csv_rows,
    rows_for_filename,
    rows_to_label_payloads,
)


def _find_vissum_test_ids() -> tuple[str, str]:
    """Reuse the Inspection/Elevation created by create_test_inspection_data.py."""
    facilities = rest_client.get_facilities().get("facilities", [])
    facility = next(f for f in facilities if f.get("short_name") == "VisSumTest")
    facility_id = facility["facility_id"]

    # Filtered client-side rather than via a facility_id query param on
    # GET /inspections — that filter isn't confirmed to exist, unlike
    # GET /elevations's facility_id param (used below).
    inspections = rest_client.get_inspections().get("inspections", [])
    inspection = next(
        i for i in inspections
        if i.get("facility_id") == facility_id and i.get("name") == "Vision Summarizer Test Inspection"
    )

    elevations = rest_client.get_facility_elevations(params={"facility_id": facility_id}).get("elevations", [])
    elevation = next(e for e in elevations if e.get("name") == "VisSumElevation")
    elevation_id = elevation.get("facility_elevation_id") or elevation.get("elevation_id")

    return inspection["inspection_id"], elevation_id


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} /path/to/image.jpg /path/to/annotations.csv [inspection_id] [elevation_id]")
        sys.exit(1)

    image_path, csv_path = sys.argv[1], sys.argv[2]
    if len(sys.argv) >= 5:
        inspection_id, elevation_id = sys.argv[3], sys.argv[4]
    else:
        inspection_id, elevation_id = _find_vissum_test_ids()

    filename = image_path.rsplit("/", 1)[-1]
    rows = rows_for_filename(parse_csv_rows(csv_path), filename)
    if not rows:
        sys.exit(f"No rows in {csv_path} match filename {filename!r}")
    print(f"Found {len(rows)} annotation(s) for {filename}\n")

    print("1. Uploading image to the inspection...")
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image = rest_client.create_inspection_image(
        inspection_id=inspection_id,
        image_bytes=image_bytes,
        filename=filename,
        facility_elevation=[elevation_id],
    )
    print(image)
    # NOTE: envelope key inferred from the facility/inspection pattern
    # (create_facility -> {"facility": {...}}) — unconfirmed live, since no
    # upload has succeeded yet. Adjust if the real key differs.
    media_id = image["image"]["media_id"]
    print(f"-> media_id = {media_id}\n")

    print("2. Persisting annotations as Geo AI detections...")
    labels = rows_to_label_payloads(rows)
    result = rest_client.create_detections(
        image_bytes=image_bytes,
        filename=filename,
        labels=labels,
        created_by="vision-summarizer-annotation-import",
    )
    print(result)


if __name__ == "__main__":
    main()
