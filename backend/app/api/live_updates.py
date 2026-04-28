"""Live workspace notification helpers."""

from __future__ import annotations

import asyncio
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
        await websocket.send_json(payload)

    async def broadcast(self, user_id: str) -> None:
        async with self._lock:
            sockets = list(self._connections.get(user_id, set()))
        if not sockets:
            return
        payload = await build_workspace_snapshot(user_id)
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception as exc:
                logger.bind(component="ws.broadcast").warning("Workspace broadcast failed: {error}", error=str(exc))
                stale.append(socket)
        for socket in stale:
            await self.disconnect(user_id, socket)


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
    await workspace_updates.broadcast(user_id)
