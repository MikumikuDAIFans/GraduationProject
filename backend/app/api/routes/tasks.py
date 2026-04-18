"""Task routes."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.live_updates import broadcast_workspace_update
from app.api.deps import TaskService, get_current_user_id, get_db_session, get_task_service
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
    task = await service.create_task(user_id=user_id, payload=payload)
    await broadcast_workspace_update(user_id)
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    payload: TaskUpdate,
    task_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> TaskRead:
    task = await service.update_task(user_id=user_id, task_id=task_id, payload=payload)
    await broadcast_workspace_update(user_id)
    return task


@router.delete("/{task_id}", response_model=OperationResult)
async def delete_task(
    task_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> OperationResult:
    await service.delete_task(user_id=user_id, task_id=task_id)
    await broadcast_workspace_update(user_id)
    return OperationResult(message="task deleted", id=task_id)


@router.get("/{task_id}/split-suggestions", response_model=dict)
async def get_split_suggestions(
    task_id: int = Path(..., ge=1),
    days_ahead: int = Query(default=7, ge=1, le=30),
    user_id: str = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Get intelligent split suggestions for a task.
    
    Analyzes the task and finds available idle slots over the next N days
    to suggest optimal splitting strategies.
    """
    from app.services.task_splitter import SmartTaskSplitter

    splitter = SmartTaskSplitter(db)

    # Get the task
    task = await service.get_task(user_id=user_id, task_id=task_id)
    if not task:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task not found")

    # Find idle slots
    now = datetime.utcnow()
    end = now + timedelta(days=days_ahead)
    slots = await splitter.get_idle_slots(
        user_id=user_id,
        start=now,
        end=end,
        min_duration=15,
    )

    # Generate split suggestions
    plan = await splitter.suggest_splits(task, slots)

    return {
        "task_id": task_id,
        "original_duration_minutes": plan.original_duration_minutes,
        "strategy_used": plan.strategy_used,
        "completion_ratio": round(plan.completion_ratio, 2),
        "suggested_splits": plan.splits,
        "notes": plan.notes,
    }
