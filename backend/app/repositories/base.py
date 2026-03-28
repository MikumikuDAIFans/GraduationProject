"""Async repository helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import InstrumentedAttribute

from app.models import UserProfile

ModelT = TypeVar("ModelT")


class AsyncRepository(Generic[ModelT]):
    """Common async CRUD primitives."""

    model: type[ModelT]

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_or_create_user(self, user_key: str) -> UserProfile:
        async with self.session_factory() as session:
            existing = await session.scalar(select(UserProfile).where(UserProfile.username == user_key))
            if existing is not None:
                return existing

            user = UserProfile(username=user_key, display_name=user_key, timezone="Asia/Shanghai")
            session.add(user)
            try:
                await session.commit()
                await session.refresh(user)
                return user
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(select(UserProfile).where(UserProfile.username == user_key))
                if existing is not None:
                    return existing
                raise

    async def list(self, statement: Select[tuple[ModelT]]) -> list[ModelT]:
        async with self.session_factory() as session:
            result = await session.scalars(statement)
            return list(result.all())

    async def get(self, *criteria: Any) -> ModelT | None:
        stmt = select(self.model).where(*criteria)
        async with self.session_factory() as session:
            return await session.scalar(stmt)

    async def create(self, payload: Mapping[str, Any]) -> ModelT:
        async with self.session_factory() as session:
            obj = self.model(**dict(payload))
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj

    async def update(self, obj: ModelT, payload: Mapping[str, Any]) -> ModelT:
        async with self.session_factory() as session:
            merged = await session.merge(obj)
            for key, value in payload.items():
                setattr(merged, key, value)
            await session.commit()
            await session.refresh(merged)
            return merged

    async def delete(self, obj: ModelT) -> None:
        async with self.session_factory() as session:
            merged = await session.merge(obj)
            await session.delete(merged)
            await session.commit()


def _ordered(statement: Select[tuple[Any]], column: InstrumentedAttribute, descending: bool = False) -> Select[tuple[Any]]:
    return statement.order_by(column.desc() if descending else column.asc())
