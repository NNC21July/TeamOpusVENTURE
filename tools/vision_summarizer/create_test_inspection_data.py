"""Manual dev script — NOT part of the test suite.

Creates the minimum chain of real objects (Facility -> Inspection -> Image)
needed for summarize_flight_inspection to have something to find, since the
sandbox ships with zero facade-inspection data. Run once per test flight you
want media attached to.

Usage:
    python tools/vision_summarizer/create_test_inspection_data.py /path/to/photo.jpg [flight_id]

flight_id defaults to a known real postflight flight in the sandbox
(0ba2c40dca916d1eb4414d1fbe059256, "NTU Sim Drone D", 2m15s).
"""

import sys
import time

from api_client import rest_client

# From existing flight records (get_flights()) — the company these test
# objects should belong to.
COMPANY_ID = "0ba2c40dca916d1eb4414d1fbe02cd55"
DEFAULT_FLIGHT_ID = "0ba2c40dca916d1eb4414d1fbe059256"


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} /path/to/photo.jpg [flight_id]")
        sys.exit(1)

    image_path = sys.argv[1]
    flight_id = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_FLIGHT_ID

    print(f"Creating test data for flight_id={flight_id} using image {image_path}\n")

    print("1. Checking for an existing test Facility to reuse...")
    existing = rest_client.get_facilities()
    existing_facilities = existing.get("facilities", []) if isinstance(existing, dict) else []
    reusable = next(
        (f for f in existing_facilities if f.get("short_name") == "VisSumTest"), None
    )
    if reusable:
        facility_id = reusable["facility_id"]
        print(f"-> reusing existing facility_id = {facility_id}\n")
    else:
        print("   none found, creating one...")
        facility = rest_client.create_facility(
            {
                "name": "Vision Summarizer Test Facility",
                "short_name": "VisSumTest",
                "company_id": COMPANY_ID,
                "type": "building",
                "status": "active",
                "address": "50 Nanyang Ave, Singapore 639798",
                "centroid": {"type": "Point", "coordinates": [103.6831, 1.3483]},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [103.6829, 1.3481],
                            [103.6833, 1.3481],
                            [103.6833, 1.3485],
                            [103.6829, 1.3485],
                            [103.6829, 1.3481],
                        ]
                    ],
                },
                "height": {"metres": 20, "stories": 5},
            }
        )
        print(facility)
        facility_id = facility["facility"]["facility_id"]
        print(f"-> facility_id = {facility_id}\n")

    print("2. Creating Inspection...")
    now_ms = int(time.time() * 1000)
    inspection = rest_client.create_inspection(
        {
            "name": "Vision Summarizer Test Inspection",
            "company_id": COMPANY_ID,
            "facility_id": facility_id,
            "type": "facade-visual",
            "flight_ids": [flight_id],
            # CONFIRMED required live (2026-08-25) despite not being marked
            # required in the Swagger doc: start_date/end_date, Unix epoch ms.
            "start_date": now_ms,
            "end_date": now_ms + 3600_000,  # +1 hour
        }
    )
    print(inspection)
    inspection_id = inspection["inspection"]["inspection_id"]
    print(f"-> inspection_id = {inspection_id}\n")

    print("2b. Testing hypothesis: moving Inspection past draft (draft -> for-approval -> inspecting)...")
    step1 = rest_client.update_inspection(inspection_id, {"status": "for-approval"})
    print(step1)
    step2 = rest_client.update_inspection(inspection_id, {"status": "inspecting"})
    print(step2)
    print()

    print("3. Checking for an existing test Facility Elevation to reuse...")
    existing_elevations_data = rest_client.get_facility_elevations(
        params={"facility_id": facility_id}
    )
    existing_elevations = (
        existing_elevations_data.get("elevations", [])
        if isinstance(existing_elevations_data, dict)
        else []
    )
    reusable_elevation = next(
        (e for e in existing_elevations if e.get("name") == "VisSumElevation"), None
    )
    if reusable_elevation:
        # Guessing the field is fully-qualified (facility_elevation_id, not
        # elevation_id) per the pattern seen on Inspection_Image
        # (inspection_image_id) — falls back to elevation_id if wrong.
        elevation_id = reusable_elevation.get("facility_elevation_id") or reusable_elevation.get(
            "elevation_id"
        )
        print(f"-> reusing existing elevation_id = {elevation_id}\n")
    else:
        print("   none found, creating one...")
        elevation = rest_client.create_facility_elevation(
            {
                "facility_id": facility_id,
                "name": "VisSumElevation",
                "description": "Test elevation for vision summarizer development",
                "height": 20,
            }
        )
        print(elevation)
        created = elevation["elevation"]
        elevation_id = created.get("facility_elevation_id") or created.get("elevation_id")
        print(f"-> elevation_id = {elevation_id}\n")

    print("4. Uploading test image...")
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image = rest_client.create_inspection_image(
        inspection_id=inspection_id,
        image_bytes=image_bytes,
        filename="test-photo.jpg",
        facility_elevation=[elevation_id],
    )
    print(image)
    print()

    print("5. Verifying end-to-end discovery via GarudaMediaClient...")
    from tools.vision_summarizer.garuda_media_client import GarudaMediaClient

    media_items = GarudaMediaClient().get_media_for_flight(flight_id=flight_id)
    print(f"-> found {len(media_items)} media item(s) for flight {flight_id}: {media_items}")


if __name__ == "__main__":
    main()
