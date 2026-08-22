from datetime import datetime, timezone
from typing import Any

import pytest

from api_client import rest_client
from tools.route_airspace_compliance.client_protocol import (
    AirspaceDataUnavailableError,
)
from tools.route_airspace_compliance.decision_types import (
    CheckResult,
    OverallDecision,
)
from tools.route_airspace_compliance.request_response_schemas import (
    RouteComplianceRequest,
    Waypoint,
)
from tools.route_airspace_compliance.service import (
    check_route_airspace_compliance,
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


def test_nfz_without_validity_becomes_airspace_data_unavailable(
    monkeypatch,
) -> None:
    def fake_get_nfzs(
        params: dict[str, Any] | None = None,
    ) -> dict:
        return {
            "nfzs": [
                {
                    "nfz_id": "GARUDA-NFZ-BROKEN-001",
                    "name": "NFZ with missing validity",
                    "restriction": "aerodrome",
                }
            ]
        }

    monkeypatch.setattr(
        rest_client,
        "get_nfzs",
        fake_get_nfzs,
    )

    client = GarudaAirspaceClient()

    with pytest.raises(
        AirspaceDataUnavailableError,
        match="invalid NFZ data",
    ):
        client.query_nfzs(
            longitude=103.8,
            latitude=1.3,
        )


def test_non_dictionary_nfz_becomes_airspace_data_unavailable(
    monkeypatch,
) -> None:
    def fake_get_nfzs(
        params: dict[str, Any] | None = None,
    ) -> dict:
        return {
            "nfzs": ["this should have been an NFZ object"],
        }

    monkeypatch.setattr(
        rest_client,
        "get_nfzs",
        fake_get_nfzs,
    )

    client = GarudaAirspaceClient()

    with pytest.raises(
        AirspaceDataUnavailableError,
        match="invalid NFZ data",
    ):
        client.query_nfzs(
            longitude=103.8,
            latitude=1.3,
        )


def test_nfz_with_invalid_timestamp_becomes_airspace_data_unavailable(
    monkeypatch,
) -> None:
    def fake_get_nfzs(
        params: dict[str, Any] | None = None,
    ) -> dict:
        return {
            "nfzs": [
                {
                    "nfz_id": "GARUDA-NFZ-BROKEN-002",
                    "name": "NFZ with an invalid timestamp",
                    "restriction": "aerodrome",
                    "validity": [
                        {
                            "start_on": "not-a-timestamp",
                            "end_on": 1787216400000,
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(
        rest_client,
        "get_nfzs",
        fake_get_nfzs,
    )

    client = GarudaAirspaceClient()

    with pytest.raises(
        AirspaceDataUnavailableError,
        match="invalid NFZ data",
    ):
        client.query_nfzs(
            longitude=103.8,
            latitude=1.3,
        )


def test_malformed_garuda_data_makes_route_decision_unknown(
    monkeypatch,
) -> None:
    def fake_get_nfzs(
        params: dict[str, Any] | None = None,
    ) -> dict:
        return {
            "nfzs": [
                {
                    "nfz_id": "GARUDA-NFZ-BROKEN-003",
                    "name": "NFZ with missing validity",
                    "restriction": "aerodrome",
                }
            ]
        }

    monkeypatch.setattr(
        rest_client,
        "get_nfzs",
        fake_get_nfzs,
    )

    request = RouteComplianceRequest(
        waypoints=[
            Waypoint(
                sequence=1,
                longitude=103.8,
                latitude=1.3,
                altitude_m=30,
            )
        ],
        planned_start_time=datetime(
            2026,
            8,
            23,
            7,
            0,
            tzinfo=timezone.utc,
        ),
        planned_end_time=datetime(
            2026,
            8,
            23,
            8,
            0,
            tzinfo=timezone.utc,
        ),
    )

    result = check_route_airspace_compliance(
        request=request,
        client=GarudaAirspaceClient(),
    )

    assert result.decision is OverallDecision.UNKNOWN
    assert result.route_clear is False
    assert len(result.waypoint_results) == 1
    assert result.waypoint_results[0].result is CheckResult.UNAVAILABLE
    assert result.required_actions == (
        "Retry when all required airspace data is available",
    )
