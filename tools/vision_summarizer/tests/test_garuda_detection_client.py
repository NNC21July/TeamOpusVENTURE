from api_client import rest_client
from tools.vision_summarizer.client_protocol import DetectionDataUnavailableError
from tools.vision_summarizer.garuda_detection_client import GarudaDetectionClient
from tools.vision_summarizer.request_response_schemas import MediaItem
import pytest


def make_media(media_type="image") -> MediaItem:
    return MediaItem(media_id="MEDIA-1", media_type=media_type)


def test_downloads_bytes_then_uploads_and_parses_detections(monkeypatch):
    calls = {}

    def fake_get_media_bytes(media_id, variant="fullscreen"):
        calls["media_id"] = media_id
        calls["variant"] = variant
        return b"fake-image-bytes"

    def fake_create_detections(*, image_bytes, filename, labels, created_by):
        calls["image_bytes"] = image_bytes
        calls["filename"] = filename
        return {
            "ml_detections": [
                {
                    "media_id": "MEDIA-1",
                    "label": {"shape": "yolo-bbox", "bbox": [0.5, 0.5, 0.1, 0.1], "object": "crack", "score": 0.9},
                }
            ]
        }

    monkeypatch.setattr(rest_client, "get_media_bytes", fake_get_media_bytes)
    monkeypatch.setattr(rest_client, "create_detections", fake_create_detections)

    client = GarudaDetectionClient()
    result = client.get_detections_for_media(media=make_media())

    assert calls["media_id"] == "MEDIA-1"
    assert calls["variant"] == "fullscreen"
    assert calls["image_bytes"] == b"fake-image-bytes"
    assert len(result) == 1
    assert result[0].object_label == "crack"
    assert result[0].bbox == (0.5, 0.5, 0.1, 0.1)


def test_unsupported_media_type_raises_unavailable_without_calling_api():
    client = GarudaDetectionClient()
    with pytest.raises(DetectionDataUnavailableError):
        client.get_detections_for_media(media=make_media(media_type="pdf"))


def test_video_is_processed_via_single_frame_like_image(monkeypatch):
    # Video isn't rejected: the Media Service's size-variant endpoints
    # already return a single representative frame for video-type media, so
    # this should hit the exact same path as an image.
    calls = {}

    def fake_get_media_bytes(media_id, variant="fullscreen"):
        calls["media_id"] = media_id
        calls["variant"] = variant
        return b"fake-frame-bytes"

    monkeypatch.setattr(rest_client, "get_media_bytes", fake_get_media_bytes)
    monkeypatch.setattr(
        rest_client,
        "create_detections",
        lambda **kwargs: {
            "ml_detections": [
                {
                    "media_id": "MEDIA-1",
                    "label": {"shape": "yolo-bbox", "bbox": [0.1, 0.1, 0.1, 0.1], "object": "person", "score": 0.7},
                }
            ]
        },
    )

    client = GarudaDetectionClient()
    result = client.get_detections_for_media(media=make_media(media_type="video"))

    assert calls["media_id"] == "MEDIA-1"
    assert calls["variant"] == "fullscreen"
    assert len(result) == 1
    assert result[0].object_label == "person"


def test_api_error_raises_detection_data_unavailable(monkeypatch):
    def fake_get_media_bytes(media_id, variant="fullscreen"):
        raise rest_client.APIError("network error")

    monkeypatch.setattr(rest_client, "get_media_bytes", fake_get_media_bytes)

    client = GarudaDetectionClient()
    with pytest.raises(DetectionDataUnavailableError):
        client.get_detections_for_media(media=make_media())


def test_get_stored_detections_reads_without_uploading(monkeypatch):
    calls = {}

    def fake_get_detections(params=None):
        calls["params"] = params
        return {
            "ml_detections": [
                {
                    "media_id": "MEDIA-1",
                    "label": {"shape": "yolo-bbox", "bbox": [0.5, 0.5, 0.1, 0.1], "object": "crack", "score": 1.0},
                }
            ]
        }

    def fail_if_called(*args, **kwargs):
        raise AssertionError("get_stored_detections_for_media must not upload/re-run detection")

    monkeypatch.setattr(rest_client, "get_detections", fake_get_detections)
    monkeypatch.setattr(rest_client, "get_media_bytes", fail_if_called)
    monkeypatch.setattr(rest_client, "create_detections", fail_if_called)

    client = GarudaDetectionClient()
    result = client.get_stored_detections_for_media(media=make_media())

    assert calls["params"] == {"media_id": "MEDIA-1"}
    assert len(result) == 1
    assert result[0].object_label == "crack"
    assert result[0].score == 1.0


def test_get_stored_detections_api_error_raises_unavailable(monkeypatch):
    def fake_get_detections(params=None):
        raise rest_client.APIError("service down")

    monkeypatch.setattr(rest_client, "get_detections", fake_get_detections)

    client = GarudaDetectionClient()
    with pytest.raises(DetectionDataUnavailableError):
        client.get_stored_detections_for_media(media=make_media())


def test_polygon_shape_is_parsed(monkeypatch):
    monkeypatch.setattr(rest_client, "get_media_bytes", lambda media_id, variant="fullscreen": b"bytes")
    monkeypatch.setattr(
        rest_client,
        "create_detections",
        lambda **kwargs: {
            "ml_detections": [
                {
                    "media_id": "MEDIA-1",
                    "label": {
                        "shape": "yolo-poly",
                        "polygon": [[0.1, 0.1], [0.2, 0.2], [0.2, 0.1]],
                        "object": "crack",
                        "score": 0.8,
                    },
                }
            ]
        },
    )

    client = GarudaDetectionClient()
    result = client.get_detections_for_media(media=make_media())

    assert result[0].polygon == ((0.1, 0.1), (0.2, 0.2), (0.2, 0.1))
    assert result[0].bbox is None
