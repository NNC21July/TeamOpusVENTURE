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

from datetime import date, datetime

from api_client import rest_client
from tools.maintenance_status.client_protocol import (
    DroneNotFoundError,
    FleetDataUnavailableError,
    ServiceRecordsUnavailableError,
)
from tools.maintenance_status.hours_calculator import (
    duration_seconds_from_parts,
    epoch_ms_to_datetime,
)
from tools.maintenance_status.request_response_schemas import (
    DroneRef,
    FlightRecord,
    ServicePlan,
    ServiceRecord,
)

PLEX_SOURCE = "plex_maintenance_plan"


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

        # Match on the drone id first. Verified live: a flight's nested drone
        # object carries `id`, and the fleet listing's `name` may differ from
        # the flight's — "NTU Sim Drone D (apm controls)" on the drone record
        # against "NTU Sim Drone D" on the flight — so name matching alone
        # silently returns zero flights and reports every airframe as unflown.
        wanted_ids = {drone.drone_id.strip().casefold()} if drone.drone_id else set()
        wanted_names = {
            value.strip().casefold()
            for value in (drone.name, drone.serial_number)
            if isinstance(value, str) and value.strip()
        }

        records: list[FlightRecord] = []
        for raw in _iter_records(payload, "flights"):
            nested = raw.get("drone") if isinstance(raw.get("drone"), dict) else {}
            flight_drone_id = nested.get("id") or nested.get("drone_id")

            if isinstance(flight_drone_id, str) and flight_drone_id.strip():
                if flight_drone_id.strip().casefold() not in wanted_ids:
                    continue
            else:
                record_name = (nested.get("name") or raw.get("drone_name") or "")
                if record_name.strip().casefold() not in wanted_names:
                    continue

            records.append(_to_flight_record(raw))
        return records

    def get_service_records(self, *, drone: DroneRef) -> list[ServiceRecord]:
        """Read logged service records from GET /aircraft/maintenance.

        Whether the endpoint filters by drone_id is unconfirmed, so the filter
        is passed AND applied again client-side. An empty list is not an error:
        it means this airframe has no recorded service, which the status rules
        handle by skipping the calendar check.
        """
        try:
            payload = rest_client.get_maintenance_records(
                params={"drone_id": drone.drone_id}
            )
        except rest_client.APIError as exc:
            raise ServiceRecordsUnavailableError(str(exc)) from exc

        records: list[ServiceRecord] = []
        for raw in _iter_records(payload, "maintenance"):
            if not _belongs_to(raw, drone):
                continue
            record = _to_service_record(raw)
            if record is not None:
                records.append(record)
        return records

    def get_service_plan(self, *, drone: DroneRef) -> ServicePlan | None:
        """Read the service interval from GET /aircraft/maintenance-plans.

        Returns None when Plex has no plan for this airframe, which lets the
        service layer fall back to the local specs table rather than treating
        an absent plan as an absent interval.
        """
        try:
            payload = rest_client.get_maintenance_plans(
                params={"drone_id": drone.drone_id}
            )
        except rest_client.APIError as exc:
            raise ServiceRecordsUnavailableError(str(exc)) from exc

        for raw in _iter_records(payload, "maintenance_plans"):
            if not _belongs_to(raw, drone):
                continue
            plan = _to_service_plan(raw, drone)
            if plan is not None and plan.interval_hours is not None:
                return plan
        return None


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
    # Only an id is available, which is the normal case: a Plex drone record
    # references its model by `drone_model_id` and carries no name. Resolve it
    # through the model catalogue, reusing the readiness tool's cache so a
    # fleet of known models costs no extra requests.
    model_id = raw.get("drone_model_id")
    if isinstance(model_id, str) and model_id.strip():
        from tools.flight_readiness.garuda_aircraft_adapter import (
            resolve_model_from_catalogue,
        )

        name, _ = resolve_model_from_catalogue(model_id.strip())
        if name:
            return name

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


def _belongs_to(raw: dict[str, Any], drone: DroneRef) -> bool:
    """True when a record is for this drone, or carries no drone reference.

    The endpoints may already filter by drone_id, in which case every record
    belongs. A record with no drone field at all is kept rather than dropped:
    dropping it could hide a service that did happen, and reporting an airframe
    as unserviced when it was serviced is the wrong direction to be wrong in.
    """
    for key in ("drone_id", "drone", "aircraft_id"):
        value = raw.get(key)
        if isinstance(value, dict):
            value = value.get("drone_id") or value.get("id") or value.get("name")
        if isinstance(value, str) and value.strip():
            candidates = {
                item.strip().casefold()
                for item in (drone.drone_id, drone.name, drone.serial_number)
                if isinstance(item, str) and item.strip()
            }
            return value.strip().casefold() in candidates
    return True


def _to_service_record(raw: dict[str, Any]) -> ServiceRecord | None:
    serviced_on = _to_date(
        _first(raw, ("serviced_on", "service_date", "date", "completed_at", "performed_at"))
    )
    if serviced_on is None:
        return None

    service_type = _first(raw, ("service_type", "type", "name", "description"))
    hours = _first(raw, ("airframe_hours", "hours_at_service", "total_flight_hours"))

    return ServiceRecord(
        serviced_on=serviced_on,
        # Free text from an API is data, never an instruction. It is carried
        # through as a plain label and never interpreted.
        service_type=str(service_type) if service_type is not None else None,
        airframe_hours_at_service=_to_float(hours),
    )


def _to_service_plan(raw: dict[str, Any], drone: DroneRef) -> ServicePlan | None:
    interval_hours = _to_float(
        _first(raw, ("interval_hours", "service_interval_hours", "hours", "interval"))
    )
    interval_months = _to_float(
        _first(raw, ("interval_months", "service_interval_months", "months"))
    )
    name = _first(raw, ("plan_name", "name", "title"))

    if interval_hours is None and interval_months is None:
        return None

    return ServicePlan(
        model=drone.model or "unknown",
        interval_hours=interval_hours,
        interval_months=int(interval_months) if interval_months is not None else None,
        plan_name=str(name) if name is not None else None,
        source=PLEX_SOURCE,
    )


def _to_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = epoch_ms_to_datetime(value)
        return parsed.date() if parsed else None
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(raw: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if raw.get(key) is not None:
            return raw[key]
    return None


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
