"""Lightweight debug observability buffers for local diagnostics."""

from __future__ import annotations

import re
import time
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer|token|password|passwd|secret|cookie|set-cookie|client_secret)",
    re.I,
)
SENSITIVE_VALUE_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]{8,}|[A-Za-z0-9_\-]{32,})",
    re.I,
)
SAFE_TOKEN_COUNT_KEYS = {"prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens"}
MAX_STRING_LENGTH = 4000
MAX_COLLECTION_ITEMS = 40


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_debug_value(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    """Return a safe-to-display copy of a debug value."""
    if key and key not in SAFE_TOKEN_COUNT_KEYS and SENSITIVE_KEY_PATTERN.search(key):
        return "[REDACTED]"
    if depth > 8:
        return "[TRUNCATED_DEPTH]"
    if isinstance(value, dict):
        items = list(value.items())
        truncated = len(items) > MAX_COLLECTION_ITEMS
        result = {
            str(item_key): redact_debug_value(item_value, key=str(item_key), depth=depth + 1)
            for item_key, item_value in items[:MAX_COLLECTION_ITEMS]
        }
        if truncated:
            result["__truncated_items__"] = len(items) - MAX_COLLECTION_ITEMS
        return result
    if isinstance(value, list):
        result = [redact_debug_value(item, depth=depth + 1) for item in value[:MAX_COLLECTION_ITEMS]]
        if len(value) > MAX_COLLECTION_ITEMS:
            result.append({"__truncated_items__": len(value) - MAX_COLLECTION_ITEMS})
        return result
    if isinstance(value, tuple):
        return [redact_debug_value(item, depth=depth + 1) for item in value[:MAX_COLLECTION_ITEMS]]
    if isinstance(value, str):
        safe = SENSITIVE_VALUE_PATTERN.sub("[REDACTED]", value)
        if len(safe) > MAX_STRING_LENGTH:
            return f"{safe[:MAX_STRING_LENGTH]}...[TRUNCATED {len(safe) - MAX_STRING_LENGTH} chars]"
        return safe
    return value


class DebugObservabilityStore:
    """Process-local ring buffers used by debug.html."""

    def __init__(self) -> None:
        self.llm_traces: deque[dict[str, Any]] = deque(maxlen=500)
        self.acceptance_runs: deque[dict[str, Any]] = deque(maxlen=100)

    def clear(self) -> None:
        self.llm_traces.clear()
        self.acceptance_runs.clear()

    def record_llm_trace(
        self,
        *,
        provider: str,
        model: str,
        purpose: str,
        status: str,
        request_payload: dict[str, Any] | None = None,
        raw_response: Any | None = None,
        parsed_result: Any | None = None,
        error: str | None = None,
        attempt: int = 1,
        started_at: float | None = None,
        request_id: str | None = None,
        session_id: int | None = None,
        message_id: int | None = None,
        fallback_from_trace_id: str | None = None,
    ) -> dict[str, Any]:
        started = started_at if started_at is not None else time.perf_counter()
        trace = {
            "trace_id": f"llm_{uuid4().hex[:12]}",
            "request_id": request_id,
            "session_id": session_id,
            "message_id": message_id,
            "purpose": purpose,
            "provider": provider,
            "model": model,
            "status": status,
            "started_at": _utc_now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "attempt": attempt,
            "request_payload_redacted": redact_debug_value(deepcopy(request_payload or {})),
            "raw_response_redacted": redact_debug_value(deepcopy(raw_response)),
            "parsed_result": redact_debug_value(deepcopy(parsed_result)),
            "error": redact_debug_value(error),
            "fallback_from_trace_id": fallback_from_trace_id,
            "redaction_applied": True,
        }
        self.llm_traces.appendleft(trace)
        return trace

    def list_llm_traces(self, *, limit: int = 100, status: str | None = None, provider: str | None = None) -> list[dict[str, Any]]:
        traces = list(self.llm_traces)
        if status:
            traces = [trace for trace in traces if trace.get("status") == status]
        if provider:
            traces = [trace for trace in traces if trace.get("provider") == provider]
        return traces[:limit]

    def get_llm_trace(self, trace_id: str) -> dict[str, Any] | None:
        return next((trace for trace in self.llm_traces if trace.get("trace_id") == trace_id), None)

    def llm_summary(self) -> dict[str, Any]:
        traces = list(self.llm_traces)
        statuses = Counter(str(trace.get("status") or "unknown") for trace in traces)
        providers = Counter(str(trace.get("provider") or "unknown") for trace in traces)
        successes = sum(count for status, count in statuses.items() if "success" in status)
        return {
            "total": len(traces),
            "success_count": successes,
            "error_count": len(traces) - successes,
            "success_rate": round(successes / len(traces) * 100, 1) if traces else 0.0,
            "status_counts": dict(statuses),
            "provider_counts": dict(providers),
            "latest": traces[0] if traces else None,
        }

    def record_acceptance_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = {
            "run_id": payload.get("run_id") or f"acceptance_{uuid4().hex[:8]}",
            "recorded_at": _utc_now(),
            **redact_debug_value(deepcopy(payload)),
        }
        self.acceptance_runs.appendleft(item)
        return item

    def list_acceptance_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return list(self.acceptance_runs)[:limit]


debug_observability = DebugObservabilityStore()
