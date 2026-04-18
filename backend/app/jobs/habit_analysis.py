"""Celery periodic jobs for habit analysis and collection."""

from __future__ import annotations

from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.vector_store import VectorStore
from app.db.session import async_session
from app.models import Event
from app.repositories.habits import HabitRepository
from app.services.habit_analyzer import HabitAnalyzer
from app.services.habit_collector import HabitCollector


@celery_app.task(bind=True, max_retries=3)
def analyze_user_habits(self, user_id: str, days_back: int = 30) -> dict:
    """Periodic task: analyze user's recent events for habit patterns.

    Runs daily via Celery Beat. Discovers recurring patterns and stores them
    in both SQLite (Habits table) and ChromaDB (vector store).
    """
    try:
        import asyncio

        async def _run_analysis():
            cutoff = datetime.utcnow() - timedelta(days=days_back)
            async with async_session() as session:
                # Fetch recent events for this user
                stmt = (
                    select(Event)
                    .where(Event.user_id == user_id)
                    .where(Event.start_time >= cutoff)
                    .where(Event.source == "local")  # Skip mirrored Google events
                )
                result = await session.execute(stmt)
                events = list(result.scalars().all())

                if len(events) < 3:
                    logger.info(f"Not enough events for habit analysis: user={user_id}, count={len(events)}")
                    return {"status": "skipped", "reason": "insufficient_events"}

                # Discover patterns
                analyzer = HabitAnalyzer()
                patterns = analyzer.discover_patterns(events, min_occurrences=3)

                if not patterns:
                    logger.info(f"No habit patterns found for user {user_id}")
                    return {"status": "no_patterns"}

                # Store patterns
                vector_store = VectorStore(persist_directory="./chroma_db")
                habit_repo = HabitRepository(session)
                collector = HabitCollector(vector_store, habit_repo)

                created_count = 0
                for pattern in patterns:
                    await collector.record_from_analysis(user_id, pattern)
                    created_count += 1

                await session.commit()

                return {
                    "status": "success",
                    "events_analyzed": len(events),
                    "patterns_found": len(patterns),
                    "habits_created": created_count,
                }

        return asyncio.run(_run_analysis())

    except Exception as exc:
        logger.error(f"Habit analysis failed for user {user_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * 5)  # Retry in 5 minutes


@celery_app.task(bind=True, max_retries=2)
def cleanup_stale_habits(self, user_id: str, stale_days: int = 90) -> dict:
    """Periodic task: reduce confidence of habits not seen recently."""
    try:
        import asyncio

        async def _run_cleanup():
            cutoff = datetime.utcnow() - timedelta(days=stale_days)
            async with async_session() as session:
                habit_repo = HabitRepository(session)
                habits = await habit_repo.get_by_user(user_id)

                reduced_count = 0
                for habit in habits:
                    if habit.last_occurrence and habit.last_occurrence < cutoff:
                        # Decay confidence by 20%
                        new_confidence = max(habit.confidence * 0.8, 0.1)
                        await habit_repo.update_confidence(habit.id, new_confidence, increment_occurrences=False)
                        reduced_count += 1

                await session.commit()
                return {
                    "status": "success",
                    "habits_checked": len(habits),
                    "confidence_reduced": reduced_count,
                }

        return asyncio.run(_run_cleanup())

    except Exception as exc:
        logger.error(f"Habit cleanup failed for user {user_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * 10)
