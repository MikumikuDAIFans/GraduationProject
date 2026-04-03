"""Helpers for safe structured logging."""

from __future__ import annotations

import re


def mask_sensitive_text(value: str | None) -> str | None:
    if value is None:
        return None
    masked = re.sub(r"(?i)(api[_-]?key|token|authorization)[=:]\s*([^\s,;]+)", r"\1=***", value)
    masked = re.sub(r"(?i)bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", "Bearer ***", masked)
    return masked
