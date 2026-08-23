"""Concrete AircraftClient backed by the shared Plex REST client.

All Plex access goes through api_client.rest_client — this tool never
authenticates or makes HTTP calls to Garuda itself. Weather is the one
exception, and it lives in sources/ for exactly that reason.

Drone resolution accepts a name, a serial number, or a drone id, because the
model will pass whatever the pilot said. Matching is case-insensitive and
tries the id last, so "Falcon 1" and "DRONE-001" both work.

Battery: Plex may or may not expose battery state on the drone record. When
the streaming bridge is available and the flight is imminent, live telemetry
is the better source; `prefer_live_telemetry` turns that on. It is off by
default because the WebSocket was not yet answering for the team's credentials.
"""

import asyncio
from typing import Any

from api_client import rest_client
from tools.flight_readiness.client_protocol import (
    AircraftDataUnavailableError,
    DroneNotFoundError,
)
from tools.flight_readiness.garuda_aircraft_adapter import (
    to_aircraft_record,
    to_battery_record,
)
from tools.flight_readiness.request_response_schemas import (
    AircraftRecord,
    BatteryRecord,
)


class GarudaAircraftClient:
    """Satisfies the AircraftClient protocol against Garuda Plex."""

    def __init__(self, *, prefer_live_telemetry: bool = False) -> None:
        self._prefer_live_telemetry = prefer_live_telemetry

    def get_aircraft(self, *, drone: str) -> AircraftRecord:
        raw = self._resolve(drone)
        try:
            return to_aircraft_record(raw)
        except (ValueError, TypeError, KeyError) as exc:
            raise AircraftDataUnavailableError(
                f"Plex returned an unusable drone record for {drone!r}"
            ) from exc

    def get_battery(self, *, drone_id: str) -> BatteryRecord:
        if self._prefer_live_telemetry:
            live = self._live_battery(drone_id)
            if live is not None:
                return live

        try:
            raw = rest_client.get_drone(drone_id)
        except rest_client.APIError as exc:
            raise AircraftDataUnavailableError(str(exc)) from exc

        battery = _extract_battery_payload(raw)
        if battery is None:
            raise AircraftDataUnavailableError(
                f"No battery state on the Plex record for drone {drone_id}"
            )
        return to_battery_record(battery)

    def _resolve(self, drone: str) -> dict[str, Any]:
        """Find one drone by name, serial or id."""
        if not drone or not drone.strip():
            raise DroneNotFoundError("No drone identifier supplied")

        needle = drone.strip().casefold()

        try:
            payload = rest_client.get_drones()
        except rest_client.APIError as exc:
            raise AircraftDataUnavailableError(str(exc)) from exc

        for candidate in _iter_drones(payload):
            for key in ("name", "serial_number", "drone_id", "id"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip().casefold() == needle:
                    return candidate

        # Not in the fleet listing: it may still be a valid id the listing
        # paginated past, so try the direct endpoint before giving up.
        try:
            return rest_client.get_drone(drone.strip())
        except rest_client.APIError as exc:
            raise DroneNotFoundError(
                f"No drone matching {drone!r} in the fleet"
            ) from exc

    def _live_battery(self, drone_id: str) -> BatteryRecord | None:
        """Best-effort read from the telemetry WebSocket.

        Returns None rather than raising: live telemetry is an upgrade over
        the last known state, never a requirement. The staleness policy already
        covers the fallback.
        """
        try:
            from api_client import streaming_bridge

            frames = asyncio.run(
                streaming_bridge.get_live_telemetry(drone_id, limit=1)
            )
        except Exception:
            return None

        frame = frames[0] if isinstance(frames, list) and frames else frames
        if not isinstance(frame, dict):
            return None

        battery = _extract_battery_payload(frame) or frame
        record = to_battery_record(battery)
        return record if record.state_of_charge is not None else None


def _iter_drones(payload: Any):
    if isinstance(payload, dict):
        for key in ("drones", "results", "items", "data"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item


def _extract_battery_payload(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the battery sub-object out of a drone record or telemetry frame."""
    for key in ("battery", "battery_state", "batteries"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]

    # Some payloads flatten the fields onto the parent instead of nesting.
    flat = {
        key: raw[key]
        for key in ("state_of_charge", "soc", "battery_percentage", "state_of_health")
        if key in raw
    }
    return flat or None
