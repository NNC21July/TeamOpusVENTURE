import json

from tools.vision_summarizer.annotation_import import (
    AnnotationRow,
    YoloRow,
    parse_csv_rows,
    parse_yolo_file,
    rows_for_filename,
    rows_to_label_payloads,
    yolo_rows_to_label_payloads,
    yolo_rows_to_raw_detections,
)

SAMPLE_YOLO = """0 0.679054 0.317568 0.155405 0.309122
0 0.977196 0.411318 0.045608 0.121622
1 0.687500 0.928209 0.108108 0.070946

"""

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


def test_parse_yolo_file(tmp_path):
    txt_path = tmp_path / "facade_inspection_test.txt"
    txt_path.write_text(SAMPLE_YOLO)

    rows = parse_yolo_file(str(txt_path))

    # Blank lines (including a trailing one) are skipped, not parsed as rows.
    assert len(rows) == 3
    assert rows[0] == YoloRow(class_id=0, x_center=0.679054, y_center=0.317568, width=0.155405, height=0.309122)
    assert rows[2].class_id == 1


def test_parse_yolo_file_tolerates_trailing_confidence_column(tmp_path):
    txt_path = tmp_path / "with_conf.txt"
    txt_path.write_text("0 0.5 0.5 0.1 0.1 0.93\n")

    rows = parse_yolo_file(str(txt_path))

    assert len(rows) == 1
    assert rows[0] == YoloRow(class_id=0, x_center=0.5, y_center=0.5, width=0.1, height=0.1)


def test_yolo_rows_to_raw_detections_uses_supplied_class_names():
    rows = [
        YoloRow(class_id=0, x_center=0.68, y_center=0.32, width=0.16, height=0.31),
        YoloRow(class_id=1, x_center=0.69, y_center=0.93, width=0.11, height=0.07),
    ]

    detections = yolo_rows_to_raw_detections(rows, media_id="MEDIA-1", class_names={0: "crack", 1: "spalling"})

    assert len(detections) == 2
    assert detections[0].object_label == "crack"
    assert detections[0].bbox == (0.68, 0.32, 0.16, 0.31)  # no conversion — already center-ratio
    assert detections[1].object_label == "spalling"
    assert all(d.media_id == "MEDIA-1" for d in detections)


def test_yolo_rows_to_label_payloads_uses_supplied_class_names():
    rows = [YoloRow(class_id=0, x_center=0.5, y_center=0.5, width=0.1, height=0.1)]

    payloads = yolo_rows_to_label_payloads(rows, class_names={0: "crack"}, score=0.8)

    label_obj = json.loads(payloads[0])
    assert label_obj["object"] == "crack"
    assert label_obj["bbox"] == [0.5, 0.5, 0.1, 0.1]
    assert label_obj["score"] == 0.8
