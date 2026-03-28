"""Task repository."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from app.models import Task
from app.repositories.base import AsyncRepository


class TaskRepository(AsyncRepository[Task]):
    model = Task

    async def list_tasks(
        self,
        *,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        await self.get_or_create_user(user_id)
        stmt = select(Task).where(Task.user_id == user_id).order_by(Task.priority.desc(), Task.id.asc()).limit(limit).offset(offset)
        return await self.list(stmt)

    async def get_task(self, task_id: int, *, user_id: str) -> Task | None:
        await self.get_or_create_user(user_id)
        return await self.get(Task.id == task_id, Task.user_id == user_id)

    async def create_task(self, payload: Mapping[str, Any]) -> Task:
        await self.get_or_create_user(str(payload["user_id"]))
        return await self.create(payload)

    async def update_task(self, task_id: int, *, user_id: str, payload: Mapping[str, Any]) -> Task | None:
        task = await self.get_task(task_id, user_id=user_id)
        if task is None:
            return None
        return await self.update(task, payload)

    async def delete_task(self, task_id: int, *, user_id: str) -> bool:
        task = await self.get_task(task_id, user_id=user_id)
        if task is None:
            return False
        await self.delete(task)
        return True
