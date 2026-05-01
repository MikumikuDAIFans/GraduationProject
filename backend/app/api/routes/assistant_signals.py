"""Assistant proactive signal routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import get_current_user_id
from app.api.schemas import (
    AssistantHeartbeatRunRead,
    AssistantHeartbeatRunRequest,
    AssistantProposalRead,
    AssistantSignalCreate,
    AssistantSignalListRead,
    AssistantSignalRead,
)
from app.core.config import get_settings
from app.services.assistant_signal_manager import AssistantSignalManager


router = APIRouter(prefix="/assistant", tags=["assistant"])


def get_signal_manager() -> AssistantSignalManager:
    return AssistantSignalManager()


@router.get("/signals", response_model=AssistantSignalListRead)
async def list_signals(
    statuses: list[str] | None = Query(default=None, alias="status"),
    signal_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantSignalManager = Depends(get_signal_manager),
) -> AssistantSignalListRead:
    items = await manager.list_signals(
        user_id=user_id,
        statuses=statuses,
        signal_type=signal_type,
        limit=limit,
    )
    return AssistantSignalListRead(items=list(items), total=len(items))


@router.get("/signals/{signal_id}", response_model=AssistantSignalRead)
async def get_signal(
    signal_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantSignalManager = Depends(get_signal_manager),
) -> AssistantSignalRead:
    return await manager.get_signal(user_id=user_id, signal_id=signal_id)


@router.post("/signals/{signal_id}/dismiss", response_model=AssistantSignalRead)
async def dismiss_signal(
    signal_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantSignalManager = Depends(get_signal_manager),
) -> AssistantSignalRead:
    return await manager.dismiss_signal(user_id=user_id, signal_id=signal_id)


@router.post("/signals/{signal_id}/proposal", response_model=AssistantProposalRead)
async def create_signal_proposal(
    signal_id: int = Path(..., ge=1),
    user_id: str = Depends(get_current_user_id),
    manager: AssistantSignalManager = Depends(get_signal_manager),
) -> AssistantProposalRead:
    """Convert a signal into a pending proposal without executing any write action."""
    return await manager.create_proposal_from_signal(user_id=user_id, signal_id=signal_id)


@router.post("/heartbeat/run", response_model=AssistantHeartbeatRunRead)
async def run_heartbeat_debug(
    payload: AssistantHeartbeatRunRequest,
    user_id: str = Depends(get_current_user_id),
    manager: AssistantSignalManager = Depends(get_signal_manager),
) -> AssistantHeartbeatRunRead:
    """Debug-only heartbeat hook that creates a signal but never executes writes."""
    settings = get_settings()
    dedup_key = payload.dedup_key or f"{payload.signal_type}:{user_id}:{datetime.now(timezone.utc).date().isoformat()}"
    signal = await manager.create_signal(
        user_id=user_id,
        payload=AssistantSignalCreate(
            signal_type=payload.signal_type,
            severity=payload.severity,
            dedup_key=dedup_key,
            target_type=payload.target_type,
            target_id=payload.target_id,
            context_json=payload.context_json or {"source": "debug_heartbeat"},
            source_job="debug_heartbeat",
        ),
    )
    return AssistantHeartbeatRunRead(
        mode=settings.assistant_proactive_mode,
        created_or_reused_signal=signal,
        message="heartbeat debug generated a signal only; proposal creation and writes still require later confirmation",
    )
