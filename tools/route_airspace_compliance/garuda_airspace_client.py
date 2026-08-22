from api_client import rest_client
from tools.route_airspace_compliance.garuda_airspace_adapter import normalize_nfz_records
from tools.route_airspace_compliance.request_response_schemas import NfzRecord
from tools.route_airspace_compliance.client_protocol import AirspaceDataUnavailableError


class GarudaAirspaceClient:
    def query_nfzs(self, *, longitude: float, latitude: float) -> list[NfzRecord]:
        try:
            response = rest_client.get_nfzs(params={
                "geo_point": f"{longitude},{latitude}"
            })
        except rest_client.APIError as exc:
            raise AirspaceDataUnavailableError(str(exc)) from exc

        nfzs = response.get("nfzs") if isinstance(response, dict) else None
        if not isinstance(nfzs, list):
            raise AirspaceDataUnavailableError(
                "Garuda NFZ API returned an unexpected response format")

        records: list[NfzRecord] = []
        for raw_nfz in nfzs:
            if not isinstance(raw_nfz, dict):
                raise AirspaceDataUnavailableError(
                    "Garuda NFZ API returned invalid NFZ data")

            validity = raw_nfz.get("validity")
            if not isinstance(validity, list) or not validity:
                raise AirspaceDataUnavailableError(
                    "Garuda NFZ API returned invalid NFZ data")

            try:
                records.extend(normalize_nfz_records(raw_nfz))
            except (
                KeyError,
                TypeError,
                ValueError,
                AttributeError,
                NotImplementedError,
                OverflowError,
            ) as exc:
                raise AirspaceDataUnavailableError(
                    "Garuda NFZ API returned invalid NFZ data") from exc

        return records
