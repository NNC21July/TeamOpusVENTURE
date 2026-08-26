from api_client import rest_client
from tools.vision_summarizer.client_protocol import MediaDataUnavailableError
from tools.vision_summarizer.garuda_media_client import GarudaMediaClient
import pytest


def test_finds_media_via_matching_inspection(monkeypatch):
    def fake_get_inspections():
        return {
            "inspections": [
                {"inspection_id": "INSP-1", "flight_ids": ["FLIGHT-1"]},
                {"inspection_id": "INSP-2", "flight_ids": ["OTHER-FLIGHT"]},
            ]
        }

    def fake_get_inspection_images(params=None):
        # CONFIRMED live: inspection_ids (plural) is a required query param.
        assert params == {"inspection_ids": ["INSP-1"]}
        return {"images": [{"inspection_image_id": "IMG-1", "inspection_id": "INSP-1", "media_id": "MEDIA-1"}]}

    monkeypatch.setattr(rest_client, "get_inspections", fake_get_inspections)
    monkeypatch.setattr(rest_client, "get_inspection_images", fake_get_inspection_images)

    client = GarudaMediaClient()
    result = client.get_media_for_flight(flight_id="FLIGHT-1")

    assert len(result) == 1
    assert result[0].media_id == "MEDIA-1"
    assert result[0].media_type == "image"


def test_no_matching_inspection_returns_empty(monkeypatch):
    def fake_get_inspections():
        return {"inspections": [{"inspection_id": "INSP-1", "flight_ids": ["OTHER-FLIGHT"]}]}

    monkeypatch.setattr(rest_client, "get_inspections", fake_get_inspections)

    client = GarudaMediaClient()
    result = client.get_media_for_flight(flight_id="FLIGHT-1")

    assert result == []


def test_images_missing_media_id_are_skipped(monkeypatch):
    def fake_get_inspections():
        return {"inspections": [{"inspection_id": "INSP-1", "flight_ids": ["FLIGHT-1"]}]}

    def fake_get_inspection_images(params=None):
        return {"images": [{"inspection_image_id": "IMG-1", "inspection_id": "INSP-1"}]}  # no media_id

    monkeypatch.setattr(rest_client, "get_inspections", fake_get_inspections)
    monkeypatch.setattr(rest_client, "get_inspection_images", fake_get_inspection_images)

    client = GarudaMediaClient()
    result = client.get_media_for_flight(flight_id="FLIGHT-1")

    assert result == []


def test_inspections_api_error_raises_media_data_unavailable(monkeypatch):
    def fake_get_inspections():
        raise rest_client.APIError("service down")

    monkeypatch.setattr(rest_client, "get_inspections", fake_get_inspections)

    client = GarudaMediaClient()
    with pytest.raises(MediaDataUnavailableError):
        client.get_media_for_flight(flight_id="FLIGHT-1")


def test_images_api_error_raises_media_data_unavailable(monkeypatch):
    def fake_get_inspections():
        return {"inspections": [{"inspection_id": "INSP-1", "flight_ids": ["FLIGHT-1"]}]}

    def fake_get_inspection_images(params=None):
        raise rest_client.APIError("service down")

    monkeypatch.setattr(rest_client, "get_inspections", fake_get_inspections)
    monkeypatch.setattr(rest_client, "get_inspection_images", fake_get_inspection_images)

    client = GarudaMediaClient()
    with pytest.raises(MediaDataUnavailableError):
        client.get_media_for_flight(flight_id="FLIGHT-1")
