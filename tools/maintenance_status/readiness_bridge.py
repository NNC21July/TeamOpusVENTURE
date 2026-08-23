"""Let Tool 2 back the readiness tool's airworthiness check.

The readiness tool declares a `MaintenanceReader` protocol expecting

    get_maintenance_status(*, drone_id: str) -> MaintenanceSnapshot

This adapter satisfies it by calling this tool's service and translating the
response into the readiness tool's record. It lives here rather than in the
readiness tool because the direction of the dependency matters: flight
readiness consumes maintenance status, not the other way round.

The translation is deliberately lossy — the readiness airworthiness predictor
needs the status and the hours, not the full audit trail.
"""

from datetime import datetime, timezone

from tools.flight_readiness.client_protocol import MaintenanceDataUnavailableError
from tools.flight_readiness.request_response_schemas import MaintenanceSnapshot
from tools.maintenance_status.client_protocol import MaintenanceClient
from tools.maintenance_status.request_response_schemas import (
    MaintenanceStatusRequest,
)
from tools.maintenance_status.service import get_drone_maintenance_status


class MaintenanceStatusReader:
    """Satisfies the readiness tool's MaintenanceReader protocol."""

    def __init__(self, *, client: MaintenanceClient) -> None:
        self._client = client

    def get_maintenance_status(self, *, drone_id: str) -> MaintenanceSnapshot:
        now = datetime.now(timezone.utc)
        try:
            response = get_drone_maintenance_status(
                request=MaintenanceStatusRequest(drone=drone_id),
                client=self._client,
                now=now,
            )
        except Exception as exc:
            # The readiness service turns this into an UNAVAILABLE check
            # rather than letting an exception end the whole assessment.
            raise MaintenanceDataUnavailableError(str(exc)) from exc

        return MaintenanceSnapshot(
            status=response.status,
            hours_since_service=response.hours_since_service,
            service_interval_hours=response.service_interval_hours,
            last_service_date=response.last_service_date,
            next_due_date=response.next_due_date,
            hours_source=response.hours_source,
            checked_at=response.data_checked_at or now,
        )
