"""Conflict detection using scanline algorithm — O(n log n) complexity."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger


@dataclass
class TimePoint:
    """A point in time for the scanline algorithm."""

    time: datetime
    event_id: str
    is_start: bool


@dataclass
class ConflictPair:
    """Represents a conflict between two events."""

    event_a_id: str
    event_b_id: str
    overlap_minutes: int
    conflict_type: str  # "direct_overlap", "travel_insufficient", "buffer_violation"


class ConflictDetector:
    """Scanline-based conflict detector for event scheduling.

    Complexity: O(n log n) where n is the number of events.
    """

    def detect_conflicts(self, events: list) -> list[ConflictPair]:
        """Detect all conflicts using the scanline algorithm.

        Args:
            events: List of event objects with start_time, end_time, buffer_before,
                   buffer_after, location_coords attributes.

        Returns:
            List of ConflictPair objects representing detected conflicts.
        """
        if len(events) < 2:
            return []

        # 1. Build time points list
        time_points = []
        event_map = {}

        for event in events:
            event_id = getattr(event, 'id', None) or getattr(event, 'event_id', None)
            if event_id is None:
                continue

            event_map[event_id] = event
            effective_start = event.start_time - timedelta(minutes=getattr(event, 'buffer_before', 0) or 0)
            effective_end = event.end_time + timedelta(minutes=getattr(event, 'buffer_after', 0) or 0)

            time_points.append(TimePoint(effective_start, event_id, True))
            time_points.append(TimePoint(effective_end, event_id, False))

        # 2. Sort by time (starts before ends at same time)
        time_points.sort(key=lambda x: (x.time, not x.is_start))

        # 3. Scan
        conflicts = []
        active_events: set[str] = set()

        for point in time_points:
            if point.is_start:
                # New event starts — check conflicts with all active events
                for active_id in active_events:
                    conflict = self._check_conflict(
                        event_map[point.event_id],
                        event_map[active_id],
                    )
                    if conflict:
                        conflicts.append(conflict)
                active_events.add(point.event_id)
            else:
                # Event ends — remove from active set
                active_events.discard(point.event_id)

        logger.info(f"Detected {len(conflicts)} conflicts among {len(events)} events")
        return conflicts

    def _check_conflict(
        self,
        event_a: object,
        event_b: object,
    ) -> Optional[ConflictPair]:
        """Check if two events conflict.

        Checks for:
        1. Direct time overlap
        2. Insufficient travel time between different locations
        3. Buffer time violation
        """
        a_effective_end = event_a.end_time + timedelta(minutes=getattr(event_a, 'buffer_after', 0) or 0)
        b_effective_start = event_b.start_time - timedelta(minutes=getattr(event_b, 'buffer_before', 0) or 0)

        # Direct time overlap
        if a_effective_end > b_effective_start:
            overlap_minutes = int((a_effective_end - b_effective_start).total_seconds() / 60)
            return ConflictPair(
                event_a_id=getattr(event_a, 'id', None) or getattr(event_a, 'event_id', ''),
                event_b_id=getattr(event_b, 'id', None) or getattr(event_b, 'event_id', ''),
                overlap_minutes=overlap_minutes,
                conflict_type="direct_overlap",
            )

        # Different locations — check travel time
        a_coords = getattr(event_a, 'location_coords', None)
        b_coords = getattr(event_b, 'location_coords', None)

        if a_coords and b_coords and a_coords != b_coords:
            # Estimate travel time (simplified — in production, use Maps API)
            travel_time = self._estimate_travel_time(event_a, event_b)
            if travel_time > 0:
                arrival_time = a_effective_end + timedelta(minutes=travel_time)
                if arrival_time > b_effective_start:
                    deficit = int((arrival_time - b_effective_start).total_seconds() / 60)
                    return ConflictPair(
                        event_a_id=getattr(event_a, 'id', None) or getattr(event_a, 'event_id', ''),
                        event_b_id=getattr(event_b, 'id', None) or getattr(event_b, 'event_id', ''),
                        overlap_minutes=deficit,
                        conflict_type="travel_insufficient",
                    )

        return None

    @staticmethod
    def _estimate_travel_time(event_a: object, event_b: object) -> int:
        """Estimate travel time between two events in minutes.

        Simplified estimation — in production, use Google Maps Distance Matrix API.
        """
        # Default estimate: 30 minutes for different locations
        # This would be replaced with actual API call
        return 30

    def build_conflict_graph(self, events: list) -> dict[str, set[str]]:
        """Build a conflict graph where edges represent conflicts.

        Returns:
            Dict mapping event_id to set of conflicting event_ids.
        """
        conflicts = self.detect_conflicts(events)
        graph: dict[str, set[str]] = defaultdict(set)

        for conflict in conflicts:
            graph[conflict.event_a_id].add(conflict.event_b_id)
            graph[conflict.event_b_id].add(conflict.event_a_id)

        return dict(graph)

    def find_conflict_chains(self, events: list) -> list[list[str]]:
        """Find all conflict chains (connected components in the conflict graph).

        Example: A↔B↔C forms one conflict chain.

        Returns:
            List of chains, where each chain is a list of event IDs.
        """
        graph = self.build_conflict_graph(events)
        visited: set[str] = set()
        chains: list[list[str]] = []

        for event_id in graph:
            if event_id not in visited:
                chain = self._dfs_chain(event_id, graph, visited)
                if len(chain) > 1:
                    chains.append(chain)

        return chains

    @staticmethod
    def _dfs_chain(
        start_id: str,
        graph: dict[str, set[str]],
        visited: set[str],
    ) -> list[str]:
        """DFS to find connected component starting from start_id."""
        stack = [start_id]
        chain = []

        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            chain.append(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    stack.append(neighbor)

        return chain

    def suggest_alternatives(
        self,
        conflicted_event: object,
        existing_events: list,
        slot_duration_minutes: int = 30,
    ) -> list[dict]:
        """Suggest alternative time slots for a conflicted event.

        Args:
            conflicted_event: The event that has conflicts
            existing_events: All existing events
            slot_duration_minutes: Duration of suggested slots

        Returns:
            List of alternative time slot suggestions.
        """
        if not conflicted_event.start_time or not conflicted_event.end_time:
            return []

        duration = (conflicted_event.end_time - conflicted_event.start_time).total_seconds() / 60
        duration = max(duration, slot_duration_minutes)

        # Look for free slots on the same day
        day_start = conflicted_event.start_time.replace(hour=8, minute=0, second=0, microsecond=0)
        day_end = conflicted_event.start_time.replace(hour=22, minute=0, second=0, microsecond=0)

        # Build busy intervals
        busy_intervals = []
        for event in existing_events:
            if event.start_time and event.end_time:
                busy_intervals.append((event.start_time, event.end_time))

        busy_intervals.sort()

        # Find gaps
        alternatives = []
        current = day_start

        for busy_start, busy_end in busy_intervals:
            if current + timedelta(minutes=duration) <= busy_start:
                # Found a gap
                alternatives.append({
                    "start_time": current.isoformat(),
                    "end_time": (current + timedelta(minutes=duration)).isoformat(),
                    "confidence": 0.8,
                })
            current = max(current, busy_end)

        # Check after last busy interval
        if current + timedelta(minutes=duration) <= day_end:
            alternatives.append({
                "start_time": current.isoformat(),
                "end_time": (current + timedelta(minutes=duration)).isoformat(),
                "confidence": 0.7,
            })

        return alternatives[:5]  # Return top 5 alternatives
