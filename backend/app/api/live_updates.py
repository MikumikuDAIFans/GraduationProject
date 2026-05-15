"""Live workspace notification helpers."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from fastapi import WebSocket
from loguru import logger

from app.services.events import EventService
from app.services.tasks import TaskService


class WorkspaceUpdateManager:
    """Track connected notification websockets and broadcast snapshots."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._last_broadcast_at: float | None = None
        self._last_broadcast_ms: float | None = None
        self._last_broadcast_user_id: str | None = None
        self._last_broadcast_socket_count = 0
        self._broadcast_failures = 0

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            user_connections = self._connections.get(user_id)
            if not user_connections:
                return
            user_connections.discard(websocket)
            if not user_connections:
                self._connections.pop(user_id, None)

    async def send_snapshot(self, user_id: str, websocket: WebSocket) -> None:
        payload = await build_workspace_snapshot(user_id)
        try:
            await asyncio.wait_for(websocket.send_json(payload), timeout=2.0)
        except Exception as exc:
            logger.bind(component="ws.snapshot").warning("Snapshot send failed: {error}", error=str(exc))
            await self.disconnect(user_id, websocket)

    async def _send_to_socket(self, user_id: str, socket: WebSocket, payload: dict, stale: list[WebSocket]) -> None:
        try:
            await asyncio.wait_for(socket.send_json(payload), timeout=2.0)
        except Exception as exc:
            logger.bind(component="ws.broadcast").warning("Workspace broadcast failed: {error}", error=str(exc))
            stale.append(socket)

    async def broadcast(self, user_id: str) -> None:
        start_time = time.perf_counter()
        async with self._lock:
            sockets = list(self._connections.get(user_id, set()))
            
        if not sockets:
            return
            
        payload = await build_workspace_snapshot(user_id)
        stale: list[WebSocket] = []
        
        # Broadcast in parallel
        tasks = [self._send_to_socket(user_id, socket, payload, stale) for socket in sockets]
        if tasks:
            await asyncio.gather(*tasks)
            
        for socket in stale:
            await self.disconnect(user_id, socket)
        self._last_broadcast_at = time.time()
        self._last_broadcast_ms = (time.perf_counter() - start_time) * 1000
        self._last_broadcast_user_id = user_id
        self._last_broadcast_socket_count = len(sockets) - len(stale)
        self._broadcast_failures += len(stale)

        logger.bind(component="ws.broadcast").info(
            "Broadcasted snapshot to {count} clients in {ms:.2f}ms", 
            count=len(sockets) - len(stale), 
            ms=(time.perf_counter() - start_time) * 1000
        )

    def summary(self) -> dict[str, object]:
        total_connections = sum(len(items) for items in self._connections.values())
        return {
            "active_connections": total_connections,
            "users": [
                {"user_id": user_id, "connections": len(items)}
                for user_id, items in self._connections.items()
            ],
            "last_broadcast_at": self._last_broadcast_at,
            "last_broadcast_ms": round(self._last_broadcast_ms or 0.0, 2),
            "last_broadcast_user_id": self._last_broadcast_user_id,
            "last_broadcast_socket_count": self._last_broadcast_socket_count,
            "broadcast_failures": self._broadcast_failures,
        }


async def build_workspace_snapshot(user_id: str) -> dict[str, object]:
    event_service = EventService()
    task_service = TaskService()

    events = await event_service.list_events(user_id=user_id)
    tasks = await task_service.list_tasks(user_id=user_id)

    return {
        "type": "workspace_snapshot",
        "events": [item.model_dump(mode="json") for item in events],
        "tasks": [item.model_dump(mode="json") for item in tasks],
    }


workspace_updates = WorkspaceUpdateManager()


async def broadcast_workspace_update(user_id: str) -> None:
    # Fire and forget instead of blocking the main thread!
    asyncio.create_task(workspace_updates.broadcast(user_id))
