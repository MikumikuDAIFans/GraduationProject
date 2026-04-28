"""WebSocket endpoints for live workspace updates."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from app.api.schemas import AssistantMessageCreate
from app.api.live_updates import broadcast_workspace_update, workspace_updates

from app.services.assistant import AssistantService

router = APIRouter()


@router.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket) -> None:
    user_id = websocket.query_params.get("user_id", "local-user")
    await workspace_updates.connect(user_id, websocket)

    try:
        await workspace_updates.send_snapshot(user_id, websocket)
        while True:
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        await workspace_updates.disconnect(user_id, websocket)
        return
    except Exception as exc:
        logger.bind(component="notifications.ws").warning("Notification WebSocket failed: {error}", error=str(exc))
        await workspace_updates.disconnect(user_id, websocket)


@router.websocket("/ws/assistant")
async def assistant_ws(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming assistant replies."""
    await websocket.accept()
    user_id = websocket.query_params.get("user_id", "local-user")
    assistant_service = AssistantService()

    try:
        while True:
            data = await websocket.receive_json()
            message = str(data.get("message", "") or "")
            session_id = data.get("session_id")

            if not message.strip():
                await websocket.send_json({"type": "error", "text": "Empty message"})
                continue

            payload = AssistantMessageCreate(session_id=session_id, message=message)
            async for chunk in assistant_service.send_message_stream(user_id, payload):
                await websocket.send_json(chunk)
            await broadcast_workspace_update(user_id)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.bind(component="assistant.ws").warning("Assistant WebSocket failed: {error}", error=str(exc))
        await websocket.send_json({"type": "error", "text": "AI 助手连接暂时失败，请稍后重试。"})
