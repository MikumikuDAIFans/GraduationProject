"""偏好学习服务 — 从用户历史行为中提取偏好模式"""

import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Event, Task, Habit
from ..core.vector_store import VectorStore

logger = logging.getLogger(__name__)


class PreferenceLearner:
    """从用户行为中学习偏好"""

    def __init__(self, db: AsyncSession, vector_store: Optional[VectorStore] = None):
        self.db = db
        self.vector_store = vector_store

    async def learn_from_history(self, user_id: str, days: int = 30) -> dict:
        """分析过去 N 天的事件数据，提取偏好模式"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(Event)
            .where(Event.user_id == user_id, Event.start_time >= cutoff)
            .order_by(Event.start_time)
        )
        result = await self.db.execute(stmt)
        events = result.scalars().all()

        if not events:
            logger.info(f"No events found for user {user_id} in last {days} days")
            return {}

        preferences = {
            "preferred_time_slots": self._analyze_time_patterns(events),
            "preferred_locations": self._analyze_location_patterns(events),
            "task_acceptance_rate": self._analyze_task_acceptance(events),
            "conflict_resolution_style": self._analyze_conflict_resolutions(events),
            "energy_curve": self._estimate_energy_curve(events),
        }

        # 存储到向量数据库
        if self.vector_store:
            await self._store_preferences(user_id, preferences)

        return preferences

    def _analyze_time_patterns(self, events: list[Event]) -> dict:
        """分析时间偏好：用户通常在什么时间安排什么类型的活动"""
        time_slots = defaultdict(lambda: defaultdict(int))
        event_types_by_hour = defaultdict(lambda: defaultdict(list))

        for event in events:
            hour = event.start_time.hour
            day_type = "weekday" if event.start_time.weekday() < 5 else "weekend"
            time_slots[day_type][hour] += 1
            event_types_by_hour[hour][event.event_type or "general"].append(event.title)

        # 找出高峰时段
        preferred = {}
        for day_type, hours in time_slots.items():
            sorted_hours = sorted(hours.items(), key=lambda x: x[1], reverse=True)
            preferred[day_type] = {
                "peak_hours": [h for h, _ in sorted_hours[:3]],
                "activity_distribution": {
                    hour: list(set(titles))[:5]
                    for hour, titles in event_types_by_hour.items()
                    if hour in [h for h, _ in sorted_hours[:3]]
                },
            }

        return preferred

    def _analyze_location_patterns(self, events: list[Event]) -> dict:
        """分析地点偏好"""
        locations = defaultdict(int)
        location_transitions = defaultdict(int)

        sorted_events = sorted(events, key=lambda e: e.start_time)
        for i in range(len(sorted_events) - 1):
            curr_loc = sorted_events[i].location or "unknown"
            next_loc = sorted_events[i + 1].location or "unknown"
            location_transitions[f"{curr_loc}→{next_loc}"] += 1

        for event in events:
            loc = event.location or "unknown"
            locations[loc] += 1

        top_locations = sorted(locations.items(), key=lambda x: x[1], reverse=True)[:5]
        top_transitions = sorted(
            location_transitions.items(), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "frequent_locations": dict(top_locations),
            "common_transitions": dict(top_transitions),
        }

    def _analyze_task_acceptance(self, events: list[Event]) -> dict:
        """分析任务接受率"""
        total = len(events)
        completed = sum(1 for e in events if getattr(e, "status", None) == "completed")
        cancelled = sum(1 for e in events if getattr(e, "status", None) == "cancelled")

        return {
            "total_events": total,
            "completion_rate": completed / total if total > 0 else 0,
            "cancellation_rate": cancelled / total if total > 0 else 0,
        }

    def _analyze_conflict_resolutions(self, events: list[Event]) -> dict:
        """分析冲突解决风格"""
        # 简化版：统计有多少事件被重新安排过
        rescheduled = sum(
            1
            for e in events
            if hasattr(e, "reschedule_count") and getattr(e, "reschedule_count", 0) > 0
        )

        return {
            "reschedule_frequency": rescheduled / len(events) if events else 0,
            "style": "flexible" if rescheduled > len(events) * 0.3 else "rigid",
        }

    def _estimate_energy_curve(self, events: list[Event]) -> list[float]:
        """估算用户的精力曲线（基于历史事件完成情况）"""
        hourly_completion = defaultdict(lambda: {"completed": 0, "total": 0})

        for event in events:
            hour = event.start_time.hour
            hourly_completion[hour]["total"] += 1
            if getattr(event, "status", None) == "completed":
                hourly_completion[hour]["completed"] += 1

        curve = []
        for hour in range(24):
            data = hourly_completion[hour]
            if data["total"] > 0:
                curve.append(data["completed"] / data["total"])
            else:
                curve.append(0.5)  # 默认值

        return curve

    async def _store_preferences(self, user_id: str, preferences: dict):
        """将偏好存储到向量数据库"""
        try:
            # 存储时间偏好
            for day_type, data in preferences.get("preferred_time_slots", {}).items():
                peak_hours = data.get("peak_hours", [])
                if peak_hours:
                    doc = f"用户在{day_type}的高峰时段是{peak_hours}"
                    self.vector_store.safe_add(
                        "preferences",
                        documents=[doc],
                        metadatas=[
                            {
                                "type": "time_preference",
                                "day_type": day_type,
                                "user_id": user_id,
                                "strength": 0.8,
                            }
                        ],
                        ids=[f"pref_time_{user_id}_{day_type}"],
                    )

            # 存储地点偏好
            frequent_locs = preferences.get("preferred_locations", {}).get(
                "frequent_locations", {}
            )
            for loc, count in frequent_locs.items():
                if loc != "unknown":
                    doc = f"用户经常去{loc}（{count}次）"
                    self.vector_store.safe_add(
                        "preferences",
                        documents=[doc],
                        metadatas=[
                            {
                                "type": "location_preference",
                                "location": loc,
                                "user_id": user_id,
                                "strength": min(count / 10, 1.0),
                            }
                        ],
                        ids=[f"pref_loc_{user_id}_{loc}"],
                    )

            logger.info(f"Stored preferences for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to store preferences for user {user_id}: {e}")

    async def get_preferences(self, user_id: str) -> dict:
        """获取用户偏好（优先从向量库检索，否则实时计算）"""
        if self.vector_store:
            try:
                results = self.vector_store.query(
                    "preferences",
                    query_texts=[f"用户{user_id}的偏好"],
                    n_results=10,
                    where={"user_id": user_id},
                )
                if results and results.get("documents"):
                    # 简化版：直接返回缓存的偏好
                    # 实际应用中应该解析向量检索结果
                    pass
            except Exception as e:
                logger.debug(f"Preference retrieval failed, falling back to learning: {e}")

        return await self.learn_from_history(user_id)
