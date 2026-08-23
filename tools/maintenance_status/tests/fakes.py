from tools.maintenance_status.client_protocol import (
    DroneNotFoundError,
    FleetDataUnavailableError,
    ServiceRecordsUnavailableError,
)
from tools.maintenance_status.request_response_schemas import (
    DroneRef,
    FlightRecord,
    ServiceRecord,
)


class FakeMaintenanceClient:
    def __init__(
        self,
        drone: DroneRef | None = None,
        flights: list[FlightRecord] | None = None,
        service_records: list[ServiceRecord] | None = None,
        *,
        not_found: bool = False,
        fleet_unavailable: bool = False,
        flights_unavailable: bool = False,
        service_records_unavailable: bool = False,
    ) -> None:
        self._drone = drone
        self._flights = list(flights) if flights is not None else []
        self._service_records = (
            list(service_records) if service_records is not None else []
        )
        self._not_found = not_found
        self._fleet_unavailable = fleet_unavailable
        self._flights_unavailable = flights_unavailable
        self._service_records_unavailable = service_records_unavailable
        self.drone_queries: list[str] = []
        self.flight_queries: list[str] = []

    def get_drone(self, *, drone: str) -> DroneRef:
        self.drone_queries.append(drone)
        if self._fleet_unavailable:
            raise FleetDataUnavailableError("Fake fleet service is unavailable")
        if self._not_found or self._drone is None:
            raise DroneNotFoundError(f"Fake client does not know drone {drone}")
        return self._drone

    def get_flight_records(self, *, drone: DroneRef) -> list[FlightRecord]:
        self.flight_queries.append(drone.drone_id)
        if self._flights_unavailable:
            raise FleetDataUnavailableError("Fake flight records are unavailable")
        return list(self._flights)

    def get_service_records(self, *, drone: DroneRef) -> list[ServiceRecord]:
        if self._service_records_unavailable:
            raise ServiceRecordsUnavailableError(
                "Fake maintenance service is unavailable"
            )
        return list(self._service_records)
