from typing import Protocol
from tools.route_airspace_compliance.request_response_schemas import NfzRecord

class AirspaceDataUnavailableError(RuntimeError):
    """Raised when required airspace information cannot be retrieved"""
    
class AirspaceClient(Protocol):
    # Airspace client capability required by the NFZ checker
    def query_nfzs(self, *, longitude: float, latitude: float) -> list[NfzRecord]:
        ...