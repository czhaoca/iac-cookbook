"""WebSocket endpoint for real-time resource status updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# Connected clients
_clients: set[WebSocket] = set()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Accept WebSocket connections and stream resource events."""
    await ws.accept()
    _clients.add(ws)
    try:
        while True:
            # Keep connection alive; client can send pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        _clients.discard(ws)


async def broadcast(event: dict[str, Any]) -> None:
    """Broadcast an event to all connected WebSocket clients."""
    if not _clients:
        return
    message = json.dumps(event)
    dead: list[WebSocket] = []
    for ws in _clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


def notify_resource_change(
    action: str, resource_id: str, provider_id: str, **extra: Any
) -> None:
    """Fire-and-forget resource change notification.

    Safe to call from sync code — schedules the broadcast on the running loop.
    """
    event = {
        "type": "resource_change",
        "action": action,
        "resource_id": resource_id,
        "provider_id": provider_id,
        **extra,
    }
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast(event))
    except RuntimeError:
        pass  # No running loop (CLI mode) — skip silently
