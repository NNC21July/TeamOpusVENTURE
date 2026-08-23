"""Concrete MaintenanceClient backed by the shared Plex REST client.

Field names are the ones the working MCP server already relies on:

    drones   drone_id, name, serial_number, drone_model_id, status
    flights  flight_id, status, drone.name, date (epoch ms, -1 unset),
             duration {hours, minutes, seconds}

Two consequences shape this file:

  * Flights identify their drone by NAME, not id, so matching is done on the
    name (falling back to serial) rather than the drone_id.
  * There is no maintenance endpoint on any of the three services the API
    client covers, so get_service_records returns an empty list. It is not an
    error — the airframe genuinely has no recorded service — and the service
    layer records that as an assumption rather than failing.
"""

from typing import Any

from api_client import rest_client
from tools.maintenance_status.client_protocol import (
    DroneNotFoundError,
    FleetDataUnavailableError,
)
from tools.maintenance_status.hours_calculator import (
    duration_seconds_from_parts,
    epoch_ms_to_datetime,
)
from tools.maintenance_status.request_response_schemas import (
    DroneRef,
    FlightRecord,
    ServiceRecord,
)


class GarudaMaintenanceClient:
    """Satisfies the MaintenanceClient protocol against Garuda Plex."""

    def get_drone(self, *, drone: str) -> DroneRef:
        if not drone or not drone.strip():
            raise DroneNotFoundError("No drone identifier supplied")

        needle = drone.strip().casefold()

        try:
            payload = rest_client.get_drones()
        except rest_client.APIError as exc:
            raise FleetDataUnavailableError(str(exc)) from exc

        for candidate in _iter_records(payload, "drones"):
            for key in ("name", "serial_number", "drone_id", "id"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip().casefold() == needle:
                    return _to_drone_ref(candidate)

        raise DroneNotFoundError(f"No drone matching {drone!r} in the fleet")

    def get_flight_records(self, *, drone: DroneRef) -> list[FlightRecord]:
        try:
            payload = rest_client.get_flights()
        except rest_client.APIError as exc:
            raise FleetDataUnavailableError(str(exc)) from exc

        wanted = {
            value.strip().casefold()
            for value in (drone.name, drone.serial_number)
            if isinstance(value, str) and value.strip()
        }

        records: list[FlightRecord] = []
        for raw in _iter_records(payload, "flights"):
            record = _to_flight_record(raw)
            if record.drone_name and record.drone_name.strip().casefold() in wanted:
                records.append(record)
        return records

    def get_service_records(self, *, drone: DroneRef) -> list[ServiceRecord]:
        """Always empty: no Plex service exposes maintenance records.

        Deliberately not an error. An empty list means "this airframe has no
        recorded service", which the status rules already handle by skipping
        the calendar check. When a maintenance endpoint appears, this is the
        one method that needs to change.
        """
        return []


def _to_drone_ref(raw: dict[str, Any]) -> DroneRef:
    drone_id = raw.get("drone_id") or raw.get("id")
    return DroneRef(
        drone_id=str(drone_id) if drone_id else "",
        name=raw.get("name"),
        serial_number=raw.get("serial_number"),
        model=_model_name(raw),
    )


def _model_name(raw: dict[str, Any]) -> str | None:
    for key in ("drone_model", "model", "model_name"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("name") or value.get("model_name")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    # Only an id is available. The service plan table is keyed by name, so an
    # unmapped id yields no plan, and the tool returns NEEDS_INFO rather than
    # comparing against an interval it invented.
    return None


def _to_flight_record(raw: dict[str, Any]) -> FlightRecord:
    return FlightRecord(
        flight_id=raw.get("flight_id"),
        drone_name=(raw.get("drone") or {}).get("name")
        if isinstance(raw.get("drone"), dict)
        else raw.get("drone_name"),
        status=raw.get("status"),
        flown_on=epoch_ms_to_datetime(raw.get("date")),
        duration_seconds=duration_seconds_from_parts(raw.get("duration")),
    )


def _iter_records(payload: Any, key: str):
    if isinstance(payload, dict):
        for candidate in (key, "results", "items", "data"):
            if isinstance(payload.get(candidate), list):
                payload = payload[candidate]
                break
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
