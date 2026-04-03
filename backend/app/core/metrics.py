"""In-memory application metrics."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from statistics import mean
from time import time


@dataclass
class MetricsStore:
    started_at: float = field(default_factory=time)
    request_durations_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    request_counts: Counter[str] = field(default_factory=Counter)
    last_request_ms: float | None = None


_STORE = MetricsStore()


def record_request(path: str, elapsed_ms: float) -> None:
    _STORE.request_counts[path] += 1
    _STORE.request_durations_ms.append(elapsed_ms)
    _STORE.last_request_ms = elapsed_ms


def metrics_snapshot() -> dict[str, object]:
    durations = list(_STORE.request_durations_ms)
    sorted_durations = sorted(durations)
    p95_index = max(0, int(len(sorted_durations) * 0.95) - 1) if sorted_durations else 0
    p95 = sorted_durations[p95_index] if sorted_durations else 0.0
    hottest_paths = [
        {"path": path, "count": count}
        for path, count in _STORE.request_counts.most_common(5)
    ]
    return {
        "uptime_seconds": int(time() - _STORE.started_at),
        "request_count": int(sum(_STORE.request_counts.values())),
        "last_request_ms": round(_STORE.last_request_ms or 0.0, 2),
        "avg_request_ms": round(mean(durations), 2) if durations else 0.0,
        "p95_request_ms": round(p95, 2),
        "hottest_paths": hottest_paths,
    }

