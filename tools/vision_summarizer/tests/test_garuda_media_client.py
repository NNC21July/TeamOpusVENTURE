import api_client
from tools.vision_summarizer.client_protocol import MediaDataUnavailableError
from tools.vision_summarizer.garuda_media_client import GarudaMediaClient
import pytest


def test_maps_raw_media_list_into_media_items(monkeypatch):
    def fake_get_media_for_flight(flight_id):
        return {
            "media": [
                {
                    "media_id": "MEDIA-1",
                    "media_type": "image",
                    "properties": {
                        "original": {"url": "https://media.mydronefleets.com/files/1.jpg"},
                        "exif": {"timestamp": "2026-08-01T09:14:00+08:00", "gps": [1.30, 103.80]},
                    },
                }
            ]
        }

    monkeypatch.setattr(api_client, "get_media_for_flight", fake_get_media_for_flight)

    client = GarudaMediaClient()
    result = client.get_media_for_flight(flight_id="FLIGHT-1")

    assert len(result) == 1
    item = result[0]
    assert item.media_id == "MEDIA-1"
    assert item.media_type == "image"
    assert item.url == "https://media.mydronefleets.com/files/1.jpg"
    assert item.captured_at is not None
    assert item.gps == (1.30, 103.80)


def test_prefers_original_over_lower_res_variants(monkeypatch):
    def fake_get_media_for_flight(flight_id):
        return {
            "media": [
                {
                    "media_id": "MEDIA-1",
                    "media_type": "image",
                    "properties": {
                        "thumb": {"url": "https://media.mydronefleets.com/files/thumb.jpg"},
                        "large": {"url": "https://media.mydronefleets.com/files/large.jpg"},
                        "original": {"url": "https://media.mydronefleets.com/files/orig.jpg"},
                    },
                }
            ]
        }

    monkeypatch.setattr(api_client, "get_media_for_flight", fake_get_media_for_flight)

    client = GarudaMediaClient()
    result = client.get_media_for_flight(flight_id="FLIGHT-1")

    assert result[0].url == "https://media.mydronefleets.com/files/orig.jpg"


def test_missing_optional_fields_do_not_crash(monkeypatch):
    def fake_get_media_for_flight(flight_id):
        return {"media": [{"media_id": "MEDIA-1", "media_type": "image"}]}

    monkeypatch.setattr(api_client, "get_media_for_flight", fake_get_media_for_flight)

    client = GarudaMediaClient()
    result = client.get_media_for_flight(flight_id="FLIGHT-1")

    assert result[0].url is None
    assert result[0].captured_at is None
    assert result[0].gps is None


def test_api_error_raises_media_data_unavailable(monkeypatch):
    def fake_get_media_for_flight(flight_id):
        raise api_client.APIError("service down")

    monkeypatch.setattr(api_client, "get_media_for_flight", fake_get_media_for_flight)

    client = GarudaMediaClient()
    with pytest.raises(MediaDataUnavailableError):
        client.get_media_for_flight(flight_id="FLIGHT-1")
