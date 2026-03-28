"""WebSocket endpoints for live workspace updates."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.assistant import AssistantService
from app.services.reminders import ReminderService
from app.services.suggestions import SuggestionService

router = APIRouter()


@router.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    user_id = websocket.query_params.get("user_id", "local-user")
    assistant_service = AssistantService()
    reminder_service = ReminderService()
    suggestion_service = SuggestionService()

    try:
        while True:
            reminders = await reminder_service.list_reminders(user_id=user_id)
            today = await suggestion_service.get_today_suggestions(user_id=user_id)
            next_items = await suggestion_service.get_next_suggestions(user_id=user_id)
            inbox = await assistant_service.get_inbox(user_id=user_id)
            summary = await assistant_service.get_summary(user_id=user_id)
            await websocket.send_json(
                {
                    "type": "workspace_snapshot",
                    "reminders": [item.model_dump(mode="json") for item in reminders],
                    "today_suggestions": [item.model_dump(mode="json") for item in today.items],
                    "next_suggestions": [item.model_dump(mode="json") for item in next_items.items],
                    "assistant_inbox": [item.model_dump(mode="json") for item in inbox.items],
                    "assistant_summary": summary.model_dump(mode="json"),
                }
            )
            await asyncio.sleep(8)
    except WebSocketDisconnect:
        return
