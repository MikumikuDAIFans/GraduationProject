"""Habit data access layer."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from loguru import logger
from sqlalchemy import Float, DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Habit


class HabitRepository:
    """Repository for habit CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: str,
        habit_type: str,
        description: str,
        time_pattern: Optional[str] = None,
        day_pattern: Optional[str] = None,
        location: Optional[str] = None,
        activity: Optional[str] = None,
        frequency: Optional[str] = None,
        confidence: float = 0.5,
    ) -> Habit:
        """Create a new habit record."""
        habit = Habit(
            id=str(uuid4()),
            user_id=user_id,
            habit_type=habit_type,
            description=description,
            time_pattern=time_pattern,
            day_pattern=day_pattern,
            location=location,
            activity=activity,
            frequency=frequency,
            confidence=confidence,
            occurrences=1,
        )
        self.session.add(habit)
        await self.session.commit()
        await self.session.refresh(habit)
        logger.info(f"Created habit: {habit.id} ({habit_type}: {description[:50]})")
        return habit

    async def get_by_id(self, habit_id: str) -> Optional[Habit]:
        """Get a habit by ID."""
        stmt = select(Habit).where(Habit.id == habit_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: str, habit_type: Optional[str] = None) -> list[Habit]:
        """Get all habits for a user, optionally filtered by type."""
        stmt = select(Habit).where(Habit.user_id == user_id)
        if habit_type:
            stmt = stmt.where(Habit.habit_type == habit_type)
        stmt = stmt.order_by(Habit.confidence.desc(), Habit.occurrences.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_similar(
        self,
        user_id: str,
        activity: Optional[str] = None,
        time_pattern: Optional[str] = None,
    ) -> list[Habit]:
        """Find habits similar to the given criteria."""
        stmt = select(Habit).where(Habit.user_id == user_id)
        if activity:
            stmt = stmt.where(Habit.activity.ilike(f"%{activity}%"))
        if time_pattern:
            stmt = stmt.where(Habit.time_pattern == time_pattern)
        stmt = stmt.order_by(Habit.confidence.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_confidence(self, habit_id: str, new_confidence: float, increment_occurrences: bool = True) -> Optional[Habit]:
        """Update habit confidence and optionally increment occurrence count."""
        habit = await self.get_by_id(habit_id)
        if not habit:
            return None
        habit.confidence = new_confidence
        if increment_occurrences:
            habit.occurrences += 1
        habit.last_occurrence = datetime.utcnow()
        habit.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(habit)
        return habit

    async def bulk_save_pending(self, metadatas: list[dict]) -> None:
        """Save habits to SQLite when vector store write fails."""
        for meta in metadatas:
            await self.create(
                user_id=meta.get("user_id", "default"),
                habit_type=meta.get("type", "routine"),
                description=meta.get("description", ""),
                time_pattern=meta.get("time_pattern"),
                day_pattern=meta.get("day_pattern"),
                location=meta.get("location"),
                activity=meta.get("activity"),
                frequency=meta.get("frequency"),
                confidence=meta.get("confidence", 0.5),
            )
        logger.info(f"Bulk saved {len(metadatas)} habits to SQLite (vector fallback)")
