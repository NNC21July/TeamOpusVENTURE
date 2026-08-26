"""
Minimal Garuda Plex Streaming Bridge Implementation

A streaming bridge is a component that connects to a streaming API and retrieves data in real-time. 
This implementation uses WebSockets to connect to the Garuda Plex API and fetch live telemetry and conformance data for drones.
To simplify the implementation, the functions returns a list of telemetry or conformance data instead of streaming it continuously.

The main function provides an example of how to use the streaming bridge to fetch telemetry data for a specific drone.:
`get_live_telemetry(drone_id: str, limit: int = 3)`: 
    Connects to the live telemetry WebSocket endpoint for a specific drone and retrieves a limited number of telemetry messages.

Future streaming bridge implementations can be built upon this foundation to handle continuous streaming, error handling, and other advanced features as needed.
However, for the purposes of NTUVENTURE, other functions are not needed, and this implementation is sufficient to meet the requirements of the project.
"""

from __future__ import annotations
from typing import Any
from urllib.parse import urlencode
import auth
import json
import asyncio
import websockets

BASE_URL = "wss://api.mydronefleets.com/"

class WebSocketError(Exception):
    """A WebSocket connection did not succeed. Message is safe to surface."""

async def _get_telemetry_stream(
    drone_id: str,
    limit: int = 3,
    timeout_seconds: float = 5.0,
) -> list[Any]:

    params = urlencode({
        "droneId": drone_id,
        # Get our access token from the auth module
        "access_token": auth.get_token(),
    })

    path = f"{BASE_URL}live/telemetry/web/?{params}"
    websocket = websockets.connect(path, ping_interval=30)

    try:
        messages = []
        async with websocket as ws:
            for _ in range(limit):
                try:
                    message = await asyncio.wait_for(
                        ws.recv(),
                        timeout=timeout_seconds,
                    )

                    if isinstance(message, str):
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError as exc:
                            raise WebSocketError(
                                f"Failed to decode JSON message: {exc}"
                            ) from exc
                    else:
                        data = message

                    messages.append(data)

                except asyncio.TimeoutError:
                    break

                except websockets.exceptions.ConnectionClosed as exc:
                    raise WebSocketError(
                        f"WebSocket connection closed unexpectedly: {exc}"
                    ) from exc

        return messages

    except WebSocketError:
        raise

    except Exception as exc:
        raise WebSocketError(
            f"Failed to connect to telemetry WebSocket: {exc}"
        ) from exc

if __name__ == "__main__":
    import asyncio

    drone_id = '0ba2c40dca916d1eb4414d1fbe03db83'  # Replace with your actual drone ID
    limit = 3
    timeout_seconds = 5.0

    try:
        telemetry_data = asyncio.run(
            _get_telemetry_stream(drone_id,limit, timeout_seconds)
        )
        print("Telemetry Data:", telemetry_data)
    except WebSocketError as e:
        print(f"Error: {e}")