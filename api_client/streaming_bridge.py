from __future__ import annotations
from typing import Any
import httpx
import auth
import json
import asyncio
import websockets

class WebSocketError(Exception):
    """A WebSocket connection did not succeed. Message is safe to surface."""

async def get_live_telemetry(drone_id: str, limit: int = 3) -> Any:
    params = {
        "drone_id": drone_id,
        "access_token": auth.get_token(),
    }
    path = f"wss://api.mydronefleets.com/live/telemetry/web/?{httpx.QueryParams(params)}"
    print(path)
    ws = websockets.connect(path, ping_interval=20, ping_timeout=10)

    try:
        async with ws as websocket:
            telemetry_data = []
            for _ in range(limit):
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10)
                    if isinstance(message, str):
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            raise WebSocketError(f"Received non-JSON message: {message}")
                    else:
                        data = message  # If it's already a dict or bytes, use it directly
                    telemetry_data.append(data)
                except asyncio.TimeoutError:
                    raise WebSocketError("Timeout while waiting for telemetry data.")
                except websockets.exceptions.ConnectionClosedError as exc:
                        raise WebSocketError(f"WebSocket connection closed unexpectedly: {exc}") from exc
                except websockets.exceptions.ConnectionClosedOK:
                        raise WebSocketError("WebSocket connection closed normally before receiving all telemetry data.")
                except websockets.exceptions.InvalidStatusCode as exc:
                        raise WebSocketError(f"WebSocket connection failed with status code: {exc.status_code}") from exc
            return telemetry_data
    except Exception as exc:
        raise WebSocketError(f"An error occurred while receiving telemetry data: {exc}") from exc


async def get_live_conformance(limit: int = 3) -> Any:
    params = {
    "access_token": auth.get_token(),
    }
    path = f"wss://api.mydronefleets.com/live/conformance?{httpx.QueryParams(params)}"
    ws = websockets.connect(path, ping_interval=20, ping_timeout=10)

    try:
        async with ws as websocket:
            conformance_data = []
            for _ in range(limit):
                message = await asyncio.wait_for(websocket.recv(), timeout=10)
                if isinstance(message, str):
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            raise WebSocketError(f"Received non-JSON message: {message}")
            else:
                data = message  # If it's already a dict or bytes, use it directly
            conformance_data.append(data)
            return conformance_data
    except asyncio.TimeoutError:
        raise WebSocketError("Timeout while waiting for conformance data.")
    except websockets.exceptions.ConnectionClosedError as exc:
        raise WebSocketError(f"WebSocket connection closed unexpectedly: {exc}") from exc
    except websockets.exceptions.ConnectionClosedOK:
        raise WebSocketError("WebSocket connection closed normally before receiving all conformance data.")


if __name__ == "__main__":
    drone_id = "0ba2c40dca916d1eb4414d1fbe03937b"

    try:
        conformance = asyncio.run(get_live_conformance( limit=3))
        print("Received conformance data:", conformance)
    except WebSocketError as e:
        print(e)