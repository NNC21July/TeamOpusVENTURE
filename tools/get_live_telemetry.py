from __future__ import annotations
from typing import Any

import api_client.streaming_bridge as streaming_bridge

async def get_live_telemetry(
    drone_id: str,
    limit: int = 3,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:

    try:
        messages = await streaming_bridge._get_telemetry_stream(
            drone_id,
            limit,
            timeout_seconds,
        )

        return {
            "status": "success",
            "drone_id": drone_id,
            "count": len(messages),
            "messages": messages,
        }

    except Exception as exc:
        return {
            "status": "error",
            "drone_id": drone_id,
            "error": str(exc),
        }