"""Habit collector service — three-path parallel collection with deduplication."""

from __future__ import annotations

import asyncio
from typing import Any, Optional
from uuid import uuid4

from loguru import logger

from app.core.vector_store import VectorStore
from app.repositories.habits import HabitRepository
from app.services.habit_analyzer import HabitAnalyzer


class HabitDeduplicator:
    """Handles habit deduplication and confidence fusion."""

    def __init__(self, habit_repo: HabitRepository):
        self.habit_repo = habit_repo

    async def merge(
        self,
        user_id: str,
        new_habit: dict[str, Any],
        existing: list[Any],
    ) -> tuple[bool, str]:
        """
        Merge a new habit with existing ones.

        Returns: (was_merged, habit_id)
        - If merged: updates existing habit's confidence and occurrences
        - If not merged: creates new habit record
        """
        # Find similar existing habit
        similar = await self._find_similar(user_id, new_habit, existing)

        if similar:
            # Fusion: update existing habit
            similar_id = similar.id if hasattr(similar, 'id') else similar.get('id')
            current_conf = similar.confidence if hasattr(similar, 'confidence') else similar.get('confidence', 0.5)
            current_count = similar.occurrences if hasattr(similar, 'occurrences') else similar.get('occurrences', 1)

            new_conf = new_habit.get('confidence', 0.5)
            weighted_conf = self._weighted_average(current_conf, new_conf, current_count, 1)

            await self.habit_repo.update_confidence(similar_id, weighted_conf, increment_occurrences=True)
            logger.info(f"Merged habit {similar_id}: confidence {current_conf:.2f} -> {weighted_conf:.2f}")
            return True, similar_id
        else:
            # New habit, create record
            habit_id = str(uuid4())
            new_habit_with_id = {**new_habit, 'id': habit_id}
            await self.habit_repo.create(
                user_id=user_id,
                habit_type=new_habit.get('type', 'routine'),
                description=new_habit.get('activity', ''),
                time_pattern=new_habit.get('time_pattern'),
                day_pattern=new_habit.get('day_pattern'),
                location=new_habit.get('location'),
                activity=new_habit.get('activity'),
                frequency=new_habit.get('frequency'),
                confidence=new_habit.get('confidence', 0.5),
            )
            logger.info(f"Created new habit {habit_id}: {new_habit.get('activity', '')}")
            return False, habit_id

    async def _find_similar(
        self,
        user_id: str,
        new_habit: dict[str, Any],
        existing: list[Any],
    ) -> Optional[Any]:
        """Find a similar habit in the existing list."""
        new_activity = (new_habit.get('activity') or '').lower()
        new_time = new_habit.get('time_pattern', '')

        for hab in existing:
            hab_activity = ''
            hab_time = ''
            if hasattr(hab, 'activity'):
                hab_activity = (hab.activity or '').lower()
                hab_time = hab.time_pattern or ''
            elif isinstance(hab, dict):
                hab_activity = (hab.get('activity') or '').lower()
                hab_time = hab.get('time_pattern', '')

            # Simple similarity: same activity keyword or same time pattern
            if new_activity and hab_activity:
                # Check if one contains the other
                if new_activity in hab_activity or hab_activity in new_activity:
                    return hab

            if new_time and hab_time and new_time == hab_time:
                return hab

        return None

    @staticmethod
    def _weighted_average(conf_a: float, conf_b: float, count_a: int, count_b: int) -> float:
        """Weighted average confidence."""
        total = count_a + count_b
        if total == 0:
            return conf_a
        return (conf_a * count_a + conf_b * count_b) / total


class HabitCollector:
    """Three-path habit collection: passive, active, conversational."""

    def __init__(self, vector_store: VectorStore, habit_repo: HabitRepository):
        self.vector_store = vector_store
        self.habit_repo = habit_repo
        self.deduplicator = HabitDeduplicator(habit_repo)

    async def on_event_created(self, event: Any) -> None:
        """Path 1: Passive collection — triggered on event CRUD."""
        pattern = HabitAnalyzer.extract_pattern(event)
        if not pattern:
            return

        user_id = event.user_id if hasattr(event, 'user_id') else 'default'

        # Check for similar existing habits
        existing = await self.habit_repo.find_similar(
            user_id,
            activity=pattern.get('activity'),
            time_pattern=pattern.get('time_pattern'),
        )

        merged, habit_id = await self.deduplicator.merge(user_id, pattern, existing)

        if not merged:
            # Add to vector store (only for new habits)
            self.vector_store.safe_add(
                collection='habits',
                documents=[pattern.get('activity', '')],
                metadatas=[{**pattern, 'user_id': user_id}],
                ids=[habit_id],
            )

    async def on_user_statement(self, message: str, user_id: str) -> None:
        """Path 3: Conversational collection — extract preferences from dialogue.

        This is a simplified version. In production, use LLM to extract structured preferences.
        """
        # For now, we log the statement for later analysis
        # In Phase 2, this will use LLM to extract preferences
        logger.debug(f"Conversational collection: user='{user_id}', message='{message[:50]}...'")

    async def record_from_analysis(self, user_id: str, pattern: dict[str, Any]) -> None:
        """Record a habit discovered from batch analysis (Path 2: Active collection)."""
        existing = await self.habit_repo.find_similar(
            user_id,
            activity=pattern.get('activity'),
            time_pattern=pattern.get('time_pattern'),
        )

        merged, habit_id = await self.deduplicator.merge(user_id, pattern, existing)

        if not merged:
            self.vector_store.safe_add(
                collection='habits',
                documents=[pattern.get('activity', '')],
                metadatas=[{**pattern, 'user_id': user_id}],
                ids=[habit_id],
            )
