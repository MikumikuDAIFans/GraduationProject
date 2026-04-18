"""Task service layer."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.api.schemas import TaskCreate, TaskRead, TaskUpdate
from app.db.session import get_sessionmaker
from app.repositories.events import EventRepository
from app.repositories.tasks import TaskRepository


class TaskService:
    """Task CRUD service."""

    def __init__(self) -> None:
        session_factory = get_sessionmaker()
        self.repository = TaskRepository(session_factory)
        self.event_repository = EventRepository(session_factory)

    async def list_tasks(self, user_id: str) -> list[TaskRead]:
        tasks = await self.repository.list_tasks(user_id=user_id)
        event_map = await self._linked_event_map(user_id=user_id, task_ids=[task.id for task in tasks])
        return [self._build_task_read(task, event_map.get(task.id, [])) for task in tasks]

    async def create_task(self, user_id: str, payload: TaskCreate) -> TaskRead:
        task = await self.repository.create_task({"user_id": user_id, **payload.model_dump()})
        return self._build_task_read(task, [])

    async def get_task(self, user_id: str, task_id: int) -> TaskRead | None:
        task = await self.repository.get_task(task_id, user_id=user_id)
        if task is None:
            return None
        linked_events = await self.event_repository.list_events_for_task_ids(user_id=user_id, task_ids=[task.id])
        return self._build_task_read(task, linked_events)

    async def update_task(self, user_id: str, task_id: int, payload: TaskUpdate) -> TaskRead:
        task = await self.repository.update_task(
            task_id,
            user_id=user_id,
            payload=payload.model_dump(exclude_none=True),
        )
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        linked_events = await self.event_repository.list_events_for_task_ids(user_id=user_id, task_ids=[task.id])
        return self._build_task_read(task, linked_events)

    async def delete_task(self, user_id: str, task_id: int) -> None:
        deleted = await self.repository.delete_task(task_id, user_id=user_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")

    async def sync_task_schedule_state(self, *, user_id: str, task_id: int) -> TaskRead | None:
        task = await self.repository.get_task(task_id, user_id=user_id)
        if task is None:
            return None

        linked_events = await self.event_repository.list_events_for_task_ids(user_id=user_id, task_ids=[task_id])
        scheduled_minutes = self._scheduled_minutes(linked_events)
        completed_minutes = self._completed_minutes(linked_events)
        payload: dict[str, object | None] = {}
        if (task.status or "pending") != "done":
            payload["status"] = self._derive_status(
                linked_events=linked_events,
                estimated_duration_minutes=task.estimated_duration_minutes,
                current_status=task.status,
            )
        active_events = [event for event in linked_events if (getattr(event, "status", None) or "planned") != "canceled"]
        payload["linked_event_id"] = active_events[0].id if active_events else (linked_events[0].id if linked_events else None)

        updated = await self.repository.update_task(task_id, user_id=user_id, payload=payload)
        if updated is None:
            return None
        return self._build_task_read(updated, linked_events)

    async def _linked_event_map(self, *, user_id: str, task_ids: list[int]) -> dict[int, list]:
        linked_events = await self.event_repository.list_events_for_task_ids(user_id=user_id, task_ids=task_ids)
        mapping: dict[int, list] = {task_id: [] for task_id in task_ids}
        for event in linked_events:
            if event.linked_task_id is not None:
                mapping.setdefault(event.linked_task_id, []).append(event)
        return mapping

    def _build_task_read(self, task, linked_events: list) -> TaskRead:
        scheduled_minutes = self._scheduled_minutes(linked_events)
        estimated_duration = task.estimated_duration_minutes
        remaining_minutes = None if estimated_duration is None else max(estimated_duration - scheduled_minutes, 0)
        completion_ratio = None
        if estimated_duration and estimated_duration > 0:
            completion_ratio = min(round(scheduled_minutes / estimated_duration, 2), 1.0)
        completed_minutes = self._completed_minutes(linked_events)
        completed_blocks_count = self._completed_blocks_count(linked_events)
        execution_ratio = None
        if estimated_duration and estimated_duration > 0:
            execution_ratio = min(round(completed_minutes / estimated_duration, 2), 1.0)

        return TaskRead.model_validate(
            {
                **task.__dict__,
                "scheduled_minutes": scheduled_minutes,
                "scheduled_blocks_count": len(linked_events),
                "remaining_minutes": remaining_minutes,
                "completion_ratio": completion_ratio,
                "completed_minutes": completed_minutes,
                "completed_blocks_count": completed_blocks_count,
                "execution_ratio": execution_ratio,
            }
        )

    def _scheduled_minutes(self, linked_events: list) -> int:
        total = 0
        for event in linked_events:
            if event.start_time is None or event.end_time is None:
                continue
            if (getattr(event, "status", None) or "planned") == "canceled":
                continue
            total += int((event.end_time - event.start_time).total_seconds() // 60)
        return total

    def _completed_minutes(self, linked_events: list) -> int:
        total = 0
        for event in linked_events:
            if event.start_time is None or event.end_time is None:
                continue
            if (getattr(event, "status", None) or "planned") != "completed":
                continue
            total += int((event.end_time - event.start_time).total_seconds() // 60)
        return total

    def _completed_blocks_count(self, linked_events: list) -> int:
        return sum(1 for event in linked_events if (getattr(event, "status", None) or "planned") == "completed")

    def _derive_status(
        self,
        *,
        linked_events: list,
        estimated_duration_minutes: int | None,
        current_status: str | None,
    ) -> str:
        active_events = [event for event in linked_events if (getattr(event, "status", None) or "planned") != "canceled"]
        completed_minutes = self._completed_minutes(linked_events)

        if current_status == "done":
            return "done"
        if estimated_duration_minutes and completed_minutes >= estimated_duration_minutes and active_events:
            return "done"
        if completed_minutes > 0:
            return "in_progress"
        if active_events:
            return "scheduled"
        return "pending"
