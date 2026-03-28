"""Task routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status

from app.api.deps import TaskService, get_current_user_id, get_task_service
from app.api.schemas import OperationResult, TaskCreate, TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    user_id: str = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> list[TaskRead]:
    return await service.list_tasks(user_id=user_id)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    user_id: str = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    return await service.create_task(user_id=user_id, payload=payload)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    payload: TaskUpdate,
    task_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    return await service.update_task(user_id=user_id, task_id=task_id, payload=payload)


@router.delete("/{task_id}", response_model=OperationResult)
async def delete_task(
    task_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> OperationResult:
    await service.delete_task(user_id=user_id, task_id=task_id)
    return OperationResult(message="task deleted", id=task_id)
