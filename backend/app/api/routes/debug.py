"""Debug and monitoring API endpoints."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger

from app.db.session import get_sessionmaker

router = APIRouter(prefix="/debug", tags=["debug"])

# In-memory request log (last 500 requests)
request_log: deque[dict[str, Any]] = deque(maxlen=500)

# In-memory log buffer for SSE streaming
log_buffer: deque[dict[str, Any]] = deque(maxlen=1000)
sse_subscribers: list[asyncio.Queue] = []


@router.on_event("startup")
async def startup_debug():
    logger.info("Debug endpoints initialized")


@router.get("/logs")
async def stream_logs() -> StreamingResponse:
    """Server-Sent Events endpoint for real-time log streaming."""
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
    return {
        "requests": list(request_log),
        "total": len(request_log),
    }


@router.get("/db-pool")
async def get_db_pool_status() -> dict[str, Any]:
    """Return database connection pool statistics."""
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
    try:
        from app.core.config import get_settings
        import redis.asyncio as aioredis
        
        settings = get_settings()
        redis_client = aioredis.from_url(settings.redis_url)
        info = await redis_client.info()
        
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
    import platform
    import sys
    
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "uptime": time.time(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
