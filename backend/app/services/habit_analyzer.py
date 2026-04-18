"""Habit analysis service — extracts patterns from events and user data."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from app.models import Event


class HabitAnalyzer:
    """Analyzes events to extract habit patterns."""

    @staticmethod
    def extract_pattern(event: Event) -> Optional[dict]:
        """Extract a habit pattern from a single event.

        Returns a dict with habit metadata or None if confidence is too low.
        """
        if not event.start_time:
            return None

        # Calculate confidence based on event characteristics
        confidence = 0.5

        # Recurring events have higher confidence
        if event.event_type and event.event_type != "general":
            confidence += 0.1

        # Events with location have more structure
        if event.location_name:
            confidence += 0.1

        # Fixed events are stronger signals
        if event.is_fixed:
            confidence += 0.15

        if confidence < 0.6:
            return None

        # Extract time pattern
        hour = event.start_time.hour
        minute = event.start_time.minute
        time_pattern = f"{hour:02d}:{minute:02d}"

        # Extract day pattern
        weekday = event.start_time.weekday()
        if weekday < 5:
            day_pattern = "weekday"
        else:
            day_pattern = "weekend"

        # Determine frequency hint
        frequency = "unknown"
        if event.event_type in ["meeting", "work"]:
            frequency = "weekly"
        elif event.event_type in ["exercise", "meal"]:
            frequency = "daily"

        return {
            "type": "routine",
            "time_pattern": time_pattern,
            "day_pattern": day_pattern,
            "location": event.location_name or "",
            "activity": event.title,
            "frequency": frequency,
            "confidence": confidence,
            "occurrences": 1,
            "last_occurrence": event.start_time.isoformat(),
        }

    @staticmethod
    def discover_patterns(events: list[Event], min_occurrences: int = 3) -> list[dict]:
        """Discover habit patterns from a batch of events.

        Groups events by title similarity and time patterns to find recurring habits.
        """
        # Group events by title keyword (simplified — in production, use vector similarity)
        title_groups: dict[str, list[Event]] = defaultdict(list)
        for event in events:
            # Use first 3 words as grouping key
            key = " ".join(event.title.split()[:3]).lower()
            title_groups[key].append(event)

        patterns = []
        for key, group in title_groups.items():
            if len(group) < min_occurrences:
                continue

            # Analyze time distribution
            hours = [e.start_time.hour for e in group if e.start_time]
            if not hours:
                continue

            # Most common hour
            hour_counts = defaultdict(int)
            for h in hours:
                hour_counts[h] += 1
            most_common_hour = max(hour_counts, key=hour_counts.get)

            # Day distribution
            weekdays = [e.start_time.weekday() for e in group if e.start_time]
            weekday_ratio = sum(1 for d in weekdays if d < 5) / len(weekdays) if weekdays else 0.5

            if weekday_ratio > 0.7:
                day_pattern = "weekday"
            elif weekday_ratio < 0.3:
                day_pattern = "weekend"
            else:
                day_pattern = "any"

            # Calculate confidence based on consistency
            consistency = max(hour_counts.values()) / len(group)
            confidence = min(0.5 + consistency * 0.5 + (len(group) - min_occurrences) * 0.05, 1.0)

            patterns.append({
                "type": "routine",
                "time_pattern": f"{most_common_hour:02d}:00",
                "day_pattern": day_pattern,
                "location": group[0].location_name or "",
                "activity": key,
                "frequency": "weekly" if day_pattern in ["weekday", "weekend"] else "daily",
                "confidence": round(confidence, 2),
                "occurrences": len(group),
                "last_occurrence": max(e.start_time for e in group if e.start_time).isoformat(),
            })

        logger.info(f"Discovered {len(patterns)} habit patterns from {len(events)} events")
        return patterns
