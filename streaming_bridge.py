import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import auth
import websockets
from typing import Any
import json
import asyncio
from urllib.parse import urlencode

BASE_URL = "wss://api.mydronefleets.com/"

class WebSocketError(Exception):
    """A Garuda WebSocket call did not succeed. Message is safe to surface."""

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

    path = f"{BASE_URL}live/telemetry/web?{params}"
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
            _get_telemetry_stream(drone_id, limit, timeout_seconds)
        )
        print("Telemetry Data:", telemetry_data)
    except WebSocketError as e:
        print(f"Error: {e}")