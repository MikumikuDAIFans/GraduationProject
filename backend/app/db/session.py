"""Async SQLAlchemy session helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Create or reuse the shared async SQLAlchemy engine."""
    return create_async_engine(
        get_database_url(),
        echo=False,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Create or reuse the shared async session factory."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session."""
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        yield session


async def init_db(engine: AsyncEngine | None = None) -> None:
    """Create all tables for a fresh local database."""
    active_engine = engine or get_engine()
    async with active_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose the shared engine."""
    await get_engine().dispose()

