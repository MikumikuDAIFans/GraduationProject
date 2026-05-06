"""Execute confirmed assistant proposal actions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.api.schemas import EventCreate, EventUpdate, TaskCreate, TaskUpdate
from app.models import AssistantProposal
from app.services.events import EventService
from app.services.tasks import TaskService


class AssistantActionExecutor:
    """Runs the actions from one confirmed proposal option.

    The executor does not decide whether a proposal is executable. That
    authority stays with AssistantProposal.status in AssistantProposalManager.
    """

    SUPPORTED_ACTIONS = {
        "create_event",
        "create_task",
        "create_task_with_events",
        "reschedule_event",
        "cancel_event",
        "mark_event_completed",
        "mark_task_completed",
        "acknowledge_signal",
    }

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
        rollback_stack: list[dict[str, Any]] = []
        related_task_id: int | None = None
        related_event_id: int | None = None
        for index, action in enumerate(actions, start=1):
            try:
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
                elif action_type == "create_task_with_events":
                    result = await self._create_task_with_events(user_id=user_id, action=action)
                elif action_type == "reschedule_event":
                    result = await self._reschedule_event(user_id=user_id, action=action)
                elif action_type == "cancel_event":
                    result = await self._cancel_event(user_id=user_id, action=action)
                elif action_type == "mark_event_completed":
                    result = await self._mark_event_completed(user_id=user_id, action=action)
                else:
                    result = await self._mark_task_completed(user_id=user_id, action=action)
            except HTTPException as exc:
                rollback = await self._rollback_executed_actions(user_id=user_id, rollback_stack=rollback_stack)
                if rollback:
                    detail: Any = {"error": exc.detail, "failed_action_index": index, "rollback": rollback}
                    raise HTTPException(status_code=exc.status_code, detail=detail) from exc
                raise
            except Exception as exc:
                rollback = await self._rollback_executed_actions(user_id=user_id, rollback_stack=rollback_stack)
                detail = {"error": "proposal action failed", "failed_action_index": index, "rollback": rollback}
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail) from exc

            if result.get("related_task_id") is not None and related_task_id is None:
                related_task_id = int(result["related_task_id"])
            if result.get("related_event_id") is not None and related_event_id is None:
                related_event_id = int(result["related_event_id"])
            results.append({"index": index, "type": action_type, "status": "succeeded", "result": result})
            compensation = result.get("compensation")
            if isinstance(compensation, dict):
                rollback_stack.append({"index": index, "type": action_type, "compensation": compensation})

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
        result = {"kind": "event", "related_event_id": snapshot.get("id"), "event": snapshot}
        if snapshot.get("id") is not None:
            result["compensation"] = {"type": "delete_event", "event_id": snapshot.get("id")}
        return result

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
        result = {"kind": "task", "related_task_id": snapshot.get("id"), "task": snapshot}
        if snapshot.get("id") is not None:
            result["compensation"] = {"type": "delete_task", "task_id": snapshot.get("id")}
        return result

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
        try:
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
        except HTTPException as exc:
            rollback = await self._rollback_compensation(
                user_id=user_id,
                item={
                    "index": None,
                    "type": "create_task_with_events",
                    "compensation": {
                        "type": "delete_task_with_events",
                        "task_id": task_id,
                        "event_ids": [snapshot.get("id") for snapshot in event_snapshots if snapshot.get("id") is not None],
                    },
                },
            )
            raise HTTPException(status_code=exc.status_code, detail={"error": exc.detail, "rollback": rollback}) from exc
        except Exception as exc:
            rollback = await self._rollback_compensation(
                user_id=user_id,
                item={
                    "index": None,
                    "type": "create_task_with_events",
                    "compensation": {
                        "type": "delete_task_with_events",
                        "task_id": task_id,
                        "event_ids": [snapshot.get("id") for snapshot in event_snapshots if snapshot.get("id") is not None],
                    },
                },
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "create_task_with_events failed", "rollback": rollback},
            ) from exc

        result = {
            "kind": "task_with_events",
            "related_task_id": task_id,
            "related_event_id": event_snapshots[0].get("id") if event_snapshots else None,
            "task": task_snapshot,
            "events": event_snapshots,
        }
        result["compensation"] = {
            "type": "delete_task_with_events",
            "task_id": task_id,
            "event_ids": [snapshot.get("id") for snapshot in event_snapshots if snapshot.get("id") is not None],
        }
        return result

    async def _reschedule_event(self, *, user_id: str, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        event_id = self._required_int(payload.get("event_id") or action.get("event_id"), field="event_id")
        update_payload = dict(payload.get("update") or payload)
        update_payload.pop("event_id", None)
        if not update_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reschedule_event requires update payload")
        previous = await self._event_snapshot_before_update(user_id=user_id, event_id=event_id)
        event = await self.event_service.update_event(
            user_id=user_id,
            event_id=event_id,
            payload=self._validate_event_update(update_payload),
        )
        snapshot = self._snapshot(event)
        result = {"kind": "event", "related_event_id": snapshot.get("id"), "event": snapshot}
        if previous:
            result["compensation"] = {"type": "restore_event", "event_id": event_id, "previous": previous}
        return result

    async def _cancel_event(self, *, user_id: str, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        event_id = self._required_int(payload.get("event_id") or action.get("event_id"), field="event_id")
        update_payload = dict(payload.get("update") or {})
        update_payload["status"] = "canceled"
        previous = await self._event_snapshot_before_update(user_id=user_id, event_id=event_id)
        event = await self.event_service.update_event(
            user_id=user_id,
            event_id=event_id,
            payload=self._validate_event_update(update_payload),
        )
        snapshot = self._snapshot(event)
        result = {"kind": "event", "related_event_id": snapshot.get("id"), "event": snapshot}
        if previous:
            result["compensation"] = {"type": "restore_event", "event_id": event_id, "previous": previous}
        return result

    async def _mark_event_completed(self, *, user_id: str, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        event_id = self._required_int(payload.get("event_id") or action.get("event_id"), field="event_id")
        update_payload = dict(payload.get("update") or {})
        update_payload["status"] = "completed"
        previous = await self._event_snapshot_before_update(user_id=user_id, event_id=event_id)
        event = await self.event_service.update_event(
            user_id=user_id,
            event_id=event_id,
            payload=self._validate_event_update(update_payload),
        )
        snapshot = self._snapshot(event)
        result = {"kind": "event", "related_event_id": snapshot.get("id"), "event": snapshot}
        if previous:
            result["compensation"] = {"type": "restore_event", "event_id": event_id, "previous": previous}
        return result

    async def _mark_task_completed(self, *, user_id: str, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        task_id = self._required_int(payload.get("task_id") or action.get("task_id"), field="task_id")
        update_payload = dict(payload.get("update") or {})
        update_payload["status"] = "done"
        previous = await self._task_snapshot_before_update(user_id=user_id, task_id=task_id)
        task = await self.task_service.update_task(
            user_id=user_id,
            task_id=task_id,
            payload=self._validate_task_update(update_payload),
        )
        snapshot = self._snapshot(task)
        result = {"kind": "task", "related_task_id": snapshot.get("id"), "task": snapshot}
        if previous:
            result["compensation"] = {"type": "restore_task", "task_id": task_id, "previous": previous}
        return result

    async def _event_snapshot_before_update(self, *, user_id: str, event_id: int) -> dict[str, Any] | None:
        get_event = getattr(self.event_service, "get_event", None)
        if get_event is None:
            return None
        event = await get_event(user_id=user_id, event_id=event_id)
        return self._snapshot(event)

    async def _task_snapshot_before_update(self, *, user_id: str, task_id: int) -> dict[str, Any] | None:
        get_task = getattr(self.task_service, "get_task", None)
        if get_task is None:
            return None
        task = await get_task(user_id=user_id, task_id=task_id)
        if task is None:
            return None
        return self._snapshot(task)

    async def _rollback_executed_actions(
        self,
        *,
        user_id: str,
        rollback_stack: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rollback_results: list[dict[str, Any]] = []
        for item in reversed(rollback_stack):
            try:
                rollback_results.append(await self._rollback_compensation(user_id=user_id, item=item))
            except Exception as exc:
                rollback_results.append(
                    {
                        "index": item.get("index"),
                        "type": item.get("type"),
                        "status": "rollback_failed",
                        "error": str(getattr(exc, "detail", exc)),
                    }
                )
        return rollback_results

    async def _rollback_compensation(self, *, user_id: str, item: dict[str, Any]) -> dict[str, Any]:
        compensation = dict(item.get("compensation") or {})
        compensation_type = compensation.get("type")
        if compensation_type == "restore_event":
            event_id = self._required_int(compensation.get("event_id"), field="event_id")
            previous = dict(compensation.get("previous") or {})
            payload = self._event_restore_payload(previous)
            event = await self.event_service.update_event(
                user_id=user_id,
                event_id=event_id,
                payload=self._validate_event_update(payload),
            )
            return {
                "index": item.get("index"),
                "type": item.get("type"),
                "status": "rolled_back",
                "result": {"kind": "event", "related_event_id": event_id, "event": self._snapshot(event)},
            }
        if compensation_type == "restore_task":
            task_id = self._required_int(compensation.get("task_id"), field="task_id")
            previous = dict(compensation.get("previous") or {})
            payload = self._task_restore_payload(previous)
            task = await self.task_service.update_task(
                user_id=user_id,
                task_id=task_id,
                payload=self._validate_task_update(payload),
            )
            return {
                "index": item.get("index"),
                "type": item.get("type"),
                "status": "rolled_back",
                "result": {"kind": "task", "related_task_id": task_id, "task": self._snapshot(task)},
            }
        if compensation_type == "delete_event":
            event_id = self._required_int(compensation.get("event_id"), field="event_id")
            delete_event = getattr(self.event_service, "delete_event", None)
            if delete_event is None:
                return {"index": item.get("index"), "type": item.get("type"), "status": "not_supported"}
            await delete_event(user_id=user_id, event_id=event_id)
            return {
                "index": item.get("index"),
                "type": item.get("type"),
                "status": "rolled_back",
                "result": {"kind": "event", "deleted_event_id": event_id},
            }
        if compensation_type == "delete_task":
            task_id = self._required_int(compensation.get("task_id"), field="task_id")
            delete_task = getattr(self.task_service, "delete_task", None)
            if delete_task is None:
                return {"index": item.get("index"), "type": item.get("type"), "status": "not_supported"}
            await delete_task(user_id=user_id, task_id=task_id)
            return {
                "index": item.get("index"),
                "type": item.get("type"),
                "status": "rolled_back",
                "result": {"kind": "task", "deleted_task_id": task_id},
            }
        if compensation_type == "delete_task_with_events":
            return await self._rollback_created_task_with_events(user_id=user_id, item=item, compensation=compensation)
        return {"index": item.get("index"), "type": item.get("type"), "status": "not_supported"}

    async def _rollback_created_task_with_events(
        self,
        *,
        user_id: str,
        item: dict[str, Any],
        compensation: dict[str, Any],
    ) -> dict[str, Any]:
        deleted_event_ids: list[int] = []
        deleted_task_id: int | None = None
        failures: list[dict[str, Any]] = []
        delete_event = getattr(self.event_service, "delete_event", None)
        delete_task = getattr(self.task_service, "delete_task", None)

        for raw_event_id in reversed(compensation.get("event_ids") or []):
            try:
                event_id = self._required_int(raw_event_id, field="event_id")
                if delete_event is None:
                    failures.append({"kind": "event", "id": event_id, "error": "delete_event not supported"})
                    continue
                await delete_event(user_id=user_id, event_id=event_id)
                deleted_event_ids.append(event_id)
            except Exception as exc:
                failures.append({"kind": "event", "id": raw_event_id, "error": str(getattr(exc, "detail", exc))})

        raw_task_id = compensation.get("task_id")
        if raw_task_id is not None:
            try:
                task_id = self._required_int(raw_task_id, field="task_id")
                if delete_task is None:
                    failures.append({"kind": "task", "id": task_id, "error": "delete_task not supported"})
                else:
                    await delete_task(user_id=user_id, task_id=task_id)
                    deleted_task_id = task_id
            except Exception as exc:
                failures.append({"kind": "task", "id": raw_task_id, "error": str(getattr(exc, "detail", exc))})

        return {
            "index": item.get("index"),
            "type": item.get("type"),
            "status": "rollback_failed" if failures else "rolled_back",
            "result": {
                "kind": "task_with_events",
                "deleted_event_ids": deleted_event_ids,
                "deleted_task_id": deleted_task_id,
                "failures": failures,
            },
        }

    def _event_restore_payload(self, previous: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = set(EventUpdate.model_fields)
        return {key: value for key, value in previous.items() if key in allowed_fields}

    def _task_restore_payload(self, previous: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = set(TaskUpdate.model_fields)
        return {key: value for key, value in previous.items() if key in allowed_fields}

    def _validate_event(self, payload: dict[str, Any]) -> EventCreate:
        try:
            return EventCreate.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid event payload: {exc.errors()}") from exc

    def _validate_event_update(self, payload: dict[str, Any]) -> EventUpdate:
        try:
            return EventUpdate.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid event update payload: {exc.errors()}") from exc

    def _validate_task(self, payload: dict[str, Any]) -> TaskCreate:
        try:
            return TaskCreate.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid task payload: {exc.errors()}") from exc

    def _validate_task_update(self, payload: dict[str, Any]) -> TaskUpdate:
        try:
            return TaskUpdate.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid task update payload: {exc.errors()}") from exc

    def _required_int(self, value: Any, *, field: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field} is required") from exc
        if parsed <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field} must be positive")
        return parsed

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
