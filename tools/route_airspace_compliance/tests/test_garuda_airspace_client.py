from datetime import datetime, timezone
from typing import Any

import pytest

from api_client import rest_client
from tools.route_airspace_compliance.client_protocol import (
    AirspaceDataUnavailableError,
)

garuda_client_module = pytest.importorskip(
    "tools.route_airspace_compliance.garuda_airspace_client",
)
GarudaAirspaceClient = garuda_client_module.GarudaAirspaceClient


def test_queries_nfz_endpoint_and_normalizes_records(monkeypatch) -> None:
    start_time = datetime(2026, 8, 20, 7, 0, tzinfo=timezone.utc)
    end_time = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    captured_request: dict[str, object] = {}

    def fake_get_nfzs(params: dict[str, Any] | None = None) -> dict[str, list[dict]]:
        captured_request["params"] = params
        return {
            "nfzs": [
                {
                    "nfz_id": "GARUDA-NFZ-CLIENT-001",
                    "type": "temp",
                    "restriction": "aerodrome",
                    "status": "active",
                    "name": "Client Test Aerodrome",
                    "min_altitude": 0,
                    "altitude": 120,
                    "validity": [
                        {
                            "start_on": int(start_time.timestamp() * 1000),
                            "end_on": int(end_time.timestamp() * 1000),
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(rest_client, "get_nfzs", fake_get_nfzs)

    client = GarudaAirspaceClient()
    records = client.query_nfzs(longitude=103.8, latitude=1.3)

    assert captured_request == {
        "params": {
            "geo_point": "103.8,1.3",
        },
    }
    assert len(records) == 1
    assert records[0].nfz_id == "GARUDA-NFZ-CLIENT-001"
    assert records[0].valid_from == start_time
    assert records[0].valid_until == end_time


def test_api_error_becomes_airspace_data_unavailable(monkeypatch) -> None:
    def fake_get_nfzs(params: dict[str, Any] | None = None) -> dict:
        raise rest_client.APIError("Garuda airspace service is unavailable")

    monkeypatch.setattr(rest_client, "get_nfzs", fake_get_nfzs)

    client = GarudaAirspaceClient()

    with pytest.raises(
        AirspaceDataUnavailableError,
        match="Garuda airspace service is unavailable",
    ):
        client.query_nfzs(longitude=103.8, latitude=1.3)


def test_missing_nfz_list_becomes_airspace_data_unavailable(monkeypatch) -> None:
    def fake_get_nfzs(params: dict[str, Any] | None = None) -> dict:
        return {}

    monkeypatch.setattr(rest_client, "get_nfzs", fake_get_nfzs)

    client = GarudaAirspaceClient()

    with pytest.raises(
        AirspaceDataUnavailableError,
        match="unexpected response format",
    ):
        client.query_nfzs(longitude=103.8, latitude=1.3)
