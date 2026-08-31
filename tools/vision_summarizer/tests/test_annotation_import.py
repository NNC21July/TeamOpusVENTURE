import json

from tools.vision_summarizer.annotation_import import (
    AnnotationRow,
    parse_csv_rows,
    rows_for_filename,
    rows_to_label_payloads,
)

SAMPLE_CSV = """crack,370,60,90,134,facade_inspection_test.jpg,612,408
crack,576,144,35,47,facade_inspection_test.jpg,612,408
spalling,394,367,62,26,facade_inspection_test.jpg,612,408
crack,10,10,20,20,other_photo.jpg,100,100
"""


def test_parse_csv_rows(tmp_path):
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text(SAMPLE_CSV)

    rows = parse_csv_rows(str(csv_path))

    assert len(rows) == 4
    assert rows[0].label == "crack"
    assert rows[0].x == 370
    assert rows[0].filename == "facade_inspection_test.jpg"
    assert rows[0].image_width == 612
    assert rows[0].image_height == 408


def test_rows_for_filename_filters(tmp_path):
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text(SAMPLE_CSV)
    rows = parse_csv_rows(str(csv_path))

    matched = rows_for_filename(rows, "facade_inspection_test.jpg")

    assert len(matched) == 3
    assert all(row.filename == "facade_inspection_test.jpg" for row in matched)


def test_rows_to_label_payloads_converts_top_left_pixels_to_center_ratios():
    # x/y in this CSV format are the TOP-LEFT corner, not the center — an
    # asymmetric box (offset from the image center) is required to actually
    # catch a top-left-vs-center mixup; a box centered in the frame would
    # pass either way and hide the bug.
    rows = [
        AnnotationRow(
            label="crack", x=100, y=50, w=40, h=20,
            filename="f.jpg", image_width=200, image_height=100,
        )
    ]

    payloads = rows_to_label_payloads(rows)

    assert len(payloads) == 1
    label_obj = json.loads(payloads[0])
    assert label_obj["shape"] == "yolo-bbox"
    assert label_obj["object"] == "crack"
    assert label_obj["score"] == 1.0
    x, y, w, h = label_obj["bbox"]
    # center = top-left + half the box size: (100+20)/200, (50+10)/100
    assert x == 0.6
    assert y == 0.6
    assert round(w, 3) == 0.2
    assert round(h, 3) == 0.2


def test_rows_to_label_payloads_score_override():
    row = AnnotationRow(
        label="spalling", x=0, y=0, w=10, h=10,
        filename="f.jpg", image_width=100, image_height=100,
    )

    payloads = rows_to_label_payloads([row], score=0.75)

    assert json.loads(payloads[0])["score"] == 0.75
