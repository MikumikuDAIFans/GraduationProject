"""Database configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resolve_relative_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (BACKEND_ROOT / path).resolve()


def get_sqlite_db_path() -> Path:
    """Return the resolved SQLite database file path."""
    raw_path = os.getenv("SQLITE_DB_PATH", "./data/app.db")
    path = _resolve_relative_path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_database_url() -> str:
    """Return the async SQLAlchemy database URL."""
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url
    return f"sqlite+aiosqlite:///{get_sqlite_db_path().as_posix()}"
