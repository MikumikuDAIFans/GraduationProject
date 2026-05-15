"""Assistant session/message repository."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AssistantMessage, AssistantSession
from app.repositories.base import AsyncRepository


class AssistantRepository(AsyncRepository[AssistantSession]):
    """Persistence helpers for assistant sessions and messages."""

    model = AssistantSession

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)

    async def create_session(
        self,
        *,
        user_id: str,
        session_type: str = "chat",
        title: str | None = None,
        context_json: Mapping[str, Any] | None = None,
    ) -> AssistantSession:
        await self.get_or_create_user(user_id)
        return await self.create(
            {
                "user_id": user_id,
                "session_type": session_type,
                "title": title or f"新对话 {datetime.now(timezone.utc).strftime('%m-%d %H:%M')}",
                "is_archived": False,
                "context_json": dict(context_json or {}),
            }
        )

    async def get_session(self, session_id: int, *, user_id: str) -> AssistantSession | None:
        await self.get_or_create_user(user_id)
        return await self.get(AssistantSession.id == session_id, AssistantSession.user_id == user_id)

    async def get_latest_session(self, *, user_id: str, session_type: str = "chat") -> AssistantSession | None:
        await self.get_or_create_user(user_id)
        stmt = (
            select(AssistantSession)
            .where(
                AssistantSession.user_id == user_id,
                AssistantSession.session_type == session_type,
                AssistantSession.is_archived.is_(False),
            )
            .order_by(AssistantSession.updated_at.desc(), AssistantSession.id.desc())
        )
        async with self.session_factory() as session:
            return await session.scalar(stmt)

    async def list_active_sessions(self, *, user_id: str, limit: int = 20) -> list[AssistantSession]:
        await self.get_or_create_user(user_id)
        stmt = (
            select(AssistantSession)
            .where(
                AssistantSession.user_id == user_id,
                AssistantSession.is_archived.is_(False),
            )
            .order_by(AssistantSession.updated_at.desc(), AssistantSession.id.desc())
            .limit(limit)
        )
        return await self.list(stmt)

    async def update_session_context(
        self,
        session_id: int,
        *,
        user_id: str,
        context_json: Mapping[str, Any] | None,
    ) -> AssistantSession | None:
        session = await self.get_session(session_id, user_id=user_id)
        if session is None:
            return None
        return await self.update(session, {"context_json": dict(context_json or {})})

    async def list_messages(self, session_id: int) -> list[AssistantMessage]:
        stmt = (
            select(AssistantMessage)
            .where(AssistantMessage.session_id == session_id)
            .order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc())
        )
        return await self.list(stmt)

    async def archive_session(self, session_id: int, *, user_id: str) -> bool:
        session = await self.get_session(session_id, user_id=user_id)
        if session is None:
            return False
        await self.update(session, {"is_archived": True})
        return True

    async def clear_session_messages(self, session_id: int, *, user_id: str) -> bool:
        session = await self.get_session(session_id, user_id=user_id)
        if session is None:
            return False

        async with self.session_factory() as db:
            await db.execute(delete(AssistantMessage).where(AssistantMessage.session_id == session_id))
            merged = await db.merge(session)
            merged.context_json = {}
            await db.commit()

        return True

    async def rename_session(self, session_id: int, *, user_id: str, title: str) -> AssistantSession | None:
        session = await self.get_session(session_id, user_id=user_id)
        if session is None:
            return None
        return await self.update(session, {"title": title})

    async def create_message(
        self,
        *,
        session_id: int,
        role: str,
        content: str,
        tool_calls_json: list[dict[str, Any]] | None = None,
        render_blocks_json: list[dict[str, Any]] | None = None,
    ) -> AssistantMessage:
        async with self.session_factory() as session:
            message = AssistantMessage(
                session_id=session_id,
                role=role,
                content=content,
                tool_calls_json=tool_calls_json,
                render_blocks_json=render_blocks_json,
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message
