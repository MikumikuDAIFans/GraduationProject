"""Debug and monitoring API endpoints."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.api.live_updates import workspace_updates
from app.core.config import get_settings
from app.core.metrics import metrics_snapshot
from app.db.session import get_sessionmaker
from app.models import AssistantMessage, AssistantProposal, AssistantSession, Event, Task
from app.repositories.assistant_proposals import ACTIVE_PROPOSAL_STATUSES, AssistantProposalRepository
from app.repositories.assistant_signals import AssistantSignalRepository
from app.services.assistant_proposal_manager import AssistantProposalManager
from app.services.debug_observability import debug_observability

router = APIRouter(prefix="/debug", tags=["debug"])

# In-memory request log (last 500 requests)
request_log: deque[dict[str, Any]] = deque(maxlen=500)

# In-memory log buffer for SSE streaming
log_buffer: deque[dict[str, Any]] = deque(maxlen=1000)
sse_subscribers: list[asyncio.Queue] = []


def _ensure_debug_allowed() -> None:
    settings = get_settings()
    if settings.app_env.lower() in {"production", "prod"} and not settings.debug_console_enabled:
        raise HTTPException(status_code=404, detail="debug console is disabled")


@router.get("/logs")
async def stream_logs() -> StreamingResponse:
    """Server-Sent Events endpoint for real-time log streaming."""
    _ensure_debug_allowed()
    queue: asyncio.Queue = asyncio.Queue()
    sse_subscribers.append(queue)
    
    async def event_generator() -> AsyncIterator[str]:
        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Log stream connected'})}\n\n"
            
            # Send buffered logs first
            for log_entry in list(log_buffer)[-100:]:
                yield f"data: {json.dumps(log_entry, ensure_ascii=False)}\n\n"
            
            # Stream new logs
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in sse_subscribers:
                sse_subscribers.remove(queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/requests")
async def get_recent_requests() -> dict[str, Any]:
    """Return recent request logs for the debug console."""
    _ensure_debug_allowed()
    return {
        "requests": list(request_log),
        "total": len(request_log),
    }


@router.post("/logs/clear")
async def clear_debug_logs() -> dict[str, Any]:
    """Clear process-local debug logs and traces."""
    _ensure_debug_allowed()
    request_log.clear()
    log_buffer.clear()
    debug_observability.clear()
    return {"status": "cleared"}


@router.get("/db-pool")
async def get_db_pool_status() -> dict[str, Any]:
    """Return database connection pool statistics."""
    _ensure_debug_allowed()
    try:
        from app.db.session import get_engine
        engine = get_engine()
        pool = engine.pool
        if pool:
            return {
                "pool_size": pool.size(),
                "active_connections": pool.checkedout(),
                "idle_connections": pool.checkedin(),
                "overflow": pool.overflow() if hasattr(pool, 'overflow') else 0,
                "checked_out": pool.checkedout(),
                "total_connections": pool.size(),
                "status": "healthy",
            }
        return {"status": "unknown", "message": "Pool not available"}
    except Exception as e:
        logger.error(f"Failed to get DB pool status: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/cache-stats")
async def get_cache_stats() -> dict[str, Any]:
    """Return Redis cache statistics if available."""
    _ensure_debug_allowed()
    try:
        from app.core.config import get_settings
        import redis.asyncio as aioredis
        
        settings = get_settings()
        redis_client = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        try:
            info = await redis_client.info()
        finally:
            await redis_client.aclose()
        
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0
        
        return {
            "hit_rate": f"{hit_rate:.1f}%",
            "hits": hits,
            "misses": misses,
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory_human", "-"),
            "status": "connected",
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        return {"status": "disconnected", "message": str(e)}


@router.get("/system")
async def get_system_info() -> dict[str, Any]:
    """Return system-level information."""
    _ensure_debug_allowed()
    import platform
    import sys
    
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "uptime": time.time(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/system/overview")
async def get_system_overview() -> dict[str, Any]:
    """Return a compact health overview for debug.html."""
    _ensure_debug_allowed()
    requests = list(request_log)
    errors = [item for item in requests if int(item.get("status") or 0) >= 400]
    slow = [item for item in requests if float(item.get("duration") or 0) >= get_settings().slow_request_threshold_ms]
    recent_cutoff = time.time() - 300
    recent: list[dict[str, Any]] = []
    for item in requests:
        try:
            timestamp = datetime.fromisoformat(str(item.get("timestamp")).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if timestamp >= recent_cutoff:
            recent.append(item)
    recent_errors = [item for item in recent if int(item.get("status") or 0) >= 400]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": get_settings().app_env,
        "debug_console_enabled": get_settings().debug_console_enabled,
        "metrics": metrics_snapshot(),
        "requests": {
            "total": len(requests),
            "error_count": len(errors),
            "error_rate": round(len(errors) / len(requests) * 100, 1) if requests else 0.0,
            "recent_total": len(recent),
            "recent_error_count": len(recent_errors),
            "recent_error_rate": round(len(recent_errors) / len(recent) * 100, 1) if recent else 0.0,
            "slow_count": len(slow),
            "slowest": sorted(requests, key=lambda item: float(item.get("duration") or 0), reverse=True)[:10],
        },
        "llm": debug_observability.llm_summary(),
        "websocket": workspace_updates.summary(),
    }


@router.get("/llm/traces")
async def list_llm_traces(limit: int = 100, status: str | None = None, provider: str | None = None) -> dict[str, Any]:
    """Return recent redacted LLM traces."""
    _ensure_debug_allowed()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": debug_observability.llm_summary(),
        "items": debug_observability.list_llm_traces(limit=limit, status=status, provider=provider),
    }


@router.get("/llm/traces/{trace_id}")
async def get_llm_trace(trace_id: str) -> dict[str, Any]:
    """Return one redacted LLM trace."""
    _ensure_debug_allowed()
    trace = debug_observability.get_llm_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return trace


@router.post("/llm/traces/sample")
async def record_sample_llm_trace() -> dict[str, Any]:
    """Record a redacted synthetic LLM trace for debug console self-tests."""
    _ensure_debug_allowed()
    return debug_observability.record_llm_trace(
        provider="debug-sample",
        model="observability-self-test",
        purpose="debug_console_self_test",
        status="success",
        request_id="debug-sample-request",
        session_id=0,
        message_id=0,
        request_payload={
            "messages": [
                {"role": "system", "content": "Return a compact JSON planning result."},
                {"role": "user", "content": "明天下午3点提醒我去学校"},
            ],
            "Authorization": "Bearer debug-sample-token-value-1234567890",
            "api_key": "sk-debug-sample-token",
        },
        raw_response={
            "id": "debug_sample_response",
            "choices": [{"message": {"content": "{\"intent\":\"schedule_event\",\"confidence\":0.91}"}}],
            "usage": {"prompt_tokens": 28, "completion_tokens": 8},
        },
        parsed_result={"intent": "schedule_event", "confidence": 0.91},
    )


@router.get("/websocket/summary")
async def get_websocket_summary() -> dict[str, Any]:
    """Return live workspace websocket diagnostics."""
    _ensure_debug_allowed()
    return {"generated_at": datetime.now(timezone.utc).isoformat(), **workspace_updates.summary()}


@router.get("/database/summary")
async def get_database_summary() -> dict[str, Any]:
    """Return key table counts for debug diagnostics."""
    _ensure_debug_allowed()
    session_factory = get_sessionmaker()
    tables = {
        "events": Event,
        "tasks": Task,
        "assistant_sessions": AssistantSession,
        "assistant_messages": AssistantMessage,
        "assistant_proposals": AssistantProposal,
    }
    async with session_factory() as session:
        counts: dict[str, int] = {}
        errors: dict[str, str] = {}
        for label, model in tables.items():
            try:
                counts[label] = int(await session.scalar(select(func.count()).select_from(model)) or 0)
            except SQLAlchemyError as exc:
                errors[label] = str(exc)
                counts[label] = -1
                await session.rollback()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "degraded" if errors else "ok",
        "counts": counts,
        "errors": errors,
        "sqlite_db_file": str(get_settings().sqlite_db_file),
    }


@router.get("/assistant/traces")
async def get_assistant_traces(session_id: int | None = None, limit: int = 20) -> dict[str, Any]:
    """Return recent assistant messages with render blocks and related proposals."""
    _ensure_debug_allowed()
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        message_stmt = select(AssistantMessage).order_by(AssistantMessage.id.desc()).limit(limit)
        if session_id is not None:
            message_stmt = select(AssistantMessage).where(AssistantMessage.session_id == session_id).order_by(AssistantMessage.id.desc()).limit(limit)
        messages = list((await session.scalars(message_stmt)).all())
        proposal_stmt = select(AssistantProposal).order_by(AssistantProposal.id.desc()).limit(limit)
        if session_id is not None:
            proposal_stmt = select(AssistantProposal).where(AssistantProposal.session_id == session_id).order_by(AssistantProposal.id.desc()).limit(limit)
        proposals = list((await session.scalars(proposal_stmt)).all())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "messages": [
            {
                "id": message.id,
                "session_id": message.session_id,
                "role": message.role,
                "content": message.content,
                "tool_calls_json": message.tool_calls_json,
                "render_blocks_json": message.render_blocks_json,
                "created_at": message.created_at.isoformat() if message.created_at else None,
            }
            for message in messages
        ],
        "proposals": [
            {
                "id": proposal.id,
                "session_id": proposal.session_id,
                "status": proposal.status,
                "proposal_type": proposal.proposal_type,
                "summary": proposal.summary,
                "payload_json": proposal.payload_json,
                "selected_option_id": proposal.selected_option_id,
                "related_event_id": proposal.related_event_id,
                "related_task_id": proposal.related_task_id,
                "execution_error": proposal.execution_error,
                "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
            }
            for proposal in proposals
        ],
    }


@router.get("/acceptance-runs")
async def list_acceptance_runs(limit: int = 20) -> dict[str, Any]:
    """Return process-local browser acceptance run summaries."""
    _ensure_debug_allowed()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": debug_observability.list_acceptance_runs(limit=limit),
    }


@router.post("/acceptance-runs")
async def record_acceptance_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a browser acceptance run summary."""
    _ensure_debug_allowed()
    return debug_observability.record_acceptance_run(payload)


@router.get("/assistant/proposals")
async def get_assistant_proposal_debug(user_id: str | None = None, dedup_key: str | None = None) -> dict[str, Any]:
    """Return proposal lifecycle diagnostics for the debug console."""
    _ensure_debug_allowed()
    session_factory = get_sessionmaker()
    proposal_repository = AssistantProposalRepository(session_factory)
    signal_repository = AssistantSignalRepository(session_factory)
    proposal_manager = AssistantProposalManager(proposal_repository, execute_on_confirm=False)

    expired = await proposal_manager.expire_due_proposals(user_id=user_id, limit=100)
    status_counts = await proposal_repository.count_by_status(user_id=user_id)
    active_count = sum(status_counts.get(status, 0) for status in ACTIVE_PROPOSAL_STATUSES)
    recent = await proposal_repository.list_recent_activity(user_id=user_id, limit=20)
    failed = await proposal_repository.list_execution_failures(user_id=user_id, limit=20)

    dedup: dict[str, Any] | None = None
    if dedup_key:
        proposal_hits = await proposal_repository.list_by_dedup_key(user_id=user_id or "local-user", dedup_key=dedup_key)
        signal_hit = await signal_repository.get_active_by_dedup_key(user_id=user_id or "local-user", dedup_key=dedup_key)
        dedup = {
            "dedup_key": dedup_key,
            "proposal_ids": [proposal.id for proposal in proposal_hits],
            "active_signal_id": signal_hit.id if signal_hit else None,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"user_id": user_id, "dedup_key": dedup_key},
        "expired_now": len(expired),
        "status_counts": status_counts,
        "active_statuses": list(ACTIVE_PROPOSAL_STATUSES),
        "active_count": active_count,
        "execution_failed_count": status_counts.get("execution_failed", 0),
        "recent_transitions": [
            {
                "id": proposal.id,
                "user_id": proposal.user_id,
                "status": proposal.status,
                "proposal_type": proposal.proposal_type,
                "dedup_key": proposal.dedup_key,
                "summary": proposal.summary,
                "execution_error": proposal.execution_error,
                "selected_option_id": proposal.selected_option_id,
                "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
            }
            for proposal in recent
        ],
        "recent_execution_failures": [
            {
                "id": proposal.id,
                "summary": proposal.summary,
                "execution_error": proposal.execution_error,
                "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
            }
            for proposal in failed
        ],
        "dedup": dedup,
    }


def log_request(method: str, path: str, status: int, duration_ms: float, request_id: str | None = None):
    """Record a request in the debug log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "path": path,
        "status": status,
        "duration": round(duration_ms, 2),
        "request_id": request_id,
    }
    request_log.append(entry)
    
    # Also add to log buffer for SSE
    log_entry = {
        "timestamp": entry["timestamp"],
        "level": "WARN" if duration_ms > 1000 else "INFO",
        "message": f"{method} {path} - {status} ({duration_ms:.0f}ms)",
    }
    log_buffer.append(log_entry)
    
    # Notify SSE subscribers
    for queue in sse_subscribers:
        try:
            queue.put_nowait(json.dumps(log_entry, ensure_ascii=False))
        except Exception:
            pass
