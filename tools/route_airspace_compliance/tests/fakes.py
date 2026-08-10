from tools.route_airspace_compliance.client_protocol import AirspaceDataUnavailableError
from tools.route_airspace_compliance.request_response_schemas import NfzRecord


class FakeAirspaceClient:
    def __init__(self, nfzs: list[NfzRecord] | None = None, *, unavailable: bool = False) -> None:
        self._nfzs = list(nfzs) if nfzs is not None else []
        self._unavailable = unavailable
        self.queries: list[tuple[float, float]] = []

    def query_nfzs(self, *, longitude: float, latitude: float) -> list[NfzRecord]:
        # Return prepared NFZ records or simulate unavailable data
        self.queries.append((longitude, latitude))

        if self._unavailable:
            raise AirspaceDataUnavailableError("Fake airspace data is unavailable")

        return list(self._nfzs)