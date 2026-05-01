"""Execute confirmed assistant proposal actions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.api.schemas import EventCreate, TaskCreate
from app.models import AssistantProposal
from app.services.events import EventService
from app.services.tasks import TaskService


class AssistantActionExecutor:
    """Runs the actions from one confirmed proposal option.

    The executor does not decide whether a proposal is executable. That
    authority stays with AssistantProposal.status in AssistantProposalManager.
    """

    SUPPORTED_ACTIONS = {"create_event", "create_task", "create_task_with_events", "acknowledge_signal"}

    def __init__(
        self,
        *,
        event_service: EventService | None = None,
        task_service: TaskService | None = None,
    ) -> None:
        self.event_service = event_service or EventService()
        self.task_service = task_service or TaskService()

    async def execute(self, *, user_id: str, proposal: AssistantProposal, option_id: str) -> dict[str, Any]:
        option = self._select_option(proposal, option_id)
        actions = option.get("actions") or []
        if not isinstance(actions, list) or not actions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="selected option has no executable actions")

        results: list[dict[str, Any]] = []
        related_task_id: int | None = None
        related_event_id: int | None = None
        for index, action in enumerate(actions, start=1):
            if not isinstance(action, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="action must be an object")
            action_type = str(action.get("type") or "")
            if action_type not in self.SUPPORTED_ACTIONS:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unsupported action type: {action_type}")

            if action_type == "acknowledge_signal":
                result = self._acknowledge_signal(action)
            elif action_type == "create_event":
                result = await self._create_event(user_id=user_id, action=action)
            elif action_type == "create_task":
                result = await self._create_task(user_id=user_id, action=action)
            else:
                result = await self._create_task_with_events(user_id=user_id, action=action)

            if result.get("related_task_id") is not None and related_task_id is None:
                related_task_id = int(result["related_task_id"])
            if result.get("related_event_id") is not None and related_event_id is None:
                related_event_id = int(result["related_event_id"])
            results.append({"index": index, "type": action_type, "status": "succeeded", "result": result})

        return {
            "status": "executed",
            "option_id": option_id,
            "actions": results,
            "related_task_id": related_task_id,
            "related_event_id": related_event_id,
        }

    def _select_option(self, proposal: AssistantProposal, option_id: str) -> dict[str, Any]:
        options = (proposal.payload_json or {}).get("options") or []
        for option in options:
            if isinstance(option, dict) and option.get("option_id") == option_id:
                return option
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="option not found")

    async def _create_event(self, *, user_id: str, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        event = await self.event_service.create_event(user_id=user_id, payload=self._validate_event(payload))
        snapshot = self._snapshot(event)
        return {"kind": "event", "related_event_id": snapshot.get("id"), "event": snapshot}

    def _acknowledge_signal(self, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        return {
            "kind": "signal_acknowledgement",
            "signal_id": payload.get("signal_id"),
            "signal_type": payload.get("signal_type"),
            "message": payload.get("message") or "signal acknowledged by confirmed proposal",
        }

    async def _create_task(self, *, user_id: str, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        task = await self.task_service.create_task(user_id=user_id, payload=self._validate_task(payload))
        snapshot = self._snapshot(task)
        return {"kind": "task", "related_task_id": snapshot.get("id"), "task": snapshot}

    async def _create_task_with_events(self, *, user_id: str, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        task_payload = dict(payload.get("task") or {})
        event_payloads = payload.get("events") or []
        if not task_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="create_task_with_events requires task payload")
        if not isinstance(event_payloads, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="events must be a list")

        task = await self.task_service.create_task(user_id=user_id, payload=self._validate_task(task_payload))
        task_snapshot = self._snapshot(task)
        task_id = task_snapshot.get("id")
        event_snapshots: list[dict[str, Any]] = []
        for event_payload in event_payloads:
            if not isinstance(event_payload, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="event payload must be an object")
            enriched_event_payload = dict(event_payload)
            enriched_event_payload["linked_task_id"] = task_id
            enriched_event_payload.setdefault("event_type", "focus_block")
            event = await self.event_service.create_event(
                user_id=user_id,
                payload=self._validate_event(enriched_event_payload),
            )
            event_snapshots.append(self._snapshot(event))

        return {
            "kind": "task_with_events",
            "related_task_id": task_id,
            "related_event_id": event_snapshots[0].get("id") if event_snapshots else None,
            "task": task_snapshot,
            "events": event_snapshots,
        }

    def _validate_event(self, payload: dict[str, Any]) -> EventCreate:
        try:
            return EventCreate.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid event payload: {exc.errors()}") from exc

    def _validate_task(self, payload: dict[str, Any]) -> TaskCreate:
        try:
            return TaskCreate.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid task payload: {exc.errors()}") from exc

    def _snapshot(self, item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        result: dict[str, Any] = {}
        for key, value in vars(item).items():
            if key.startswith("_") or callable(value):
                continue
            if isinstance(value, datetime):
                value = value.isoformat()
            result[key] = value
        return result
