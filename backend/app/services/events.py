"""Event service layer."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.api.schemas import EventCreate, EventRead, EventUpdate
from app.db.session import get_sessionmaker
from app.repositories.events import EventRepository
from app.repositories.profiles import UserProfileRepository
from app.repositories.reminders import ReminderRepository
from app.services.context import ContextService
from app.services.google_calendar import GoogleCalendarService
from app.services.tasks import TaskService


class EventService:
    """Event CRUD service."""

    def __init__(self) -> None:
        session_factory = get_sessionmaker()
        self.repository = EventRepository(session_factory)
        self.profile_repository = UserProfileRepository(session_factory)
        self.reminder_repository = ReminderRepository(session_factory)
        self.context_service = ContextService()
        self.google_calendar_service = GoogleCalendarService()
        self.task_service = TaskService()

    async def list_events(self, user_id: str, start=None, end=None) -> list[EventRead]:
        items = await self.repository.list_events(user_id=user_id)
        filtered = []
        for item in items:
            if start is not None and item.end_time is not None and item.end_time < start:
                continue
            if end is not None and item.start_time is not None and item.start_time > end:
                continue
            filtered.append(EventRead.model_validate(item))
        return filtered

    @staticmethod
    def _event_snapshot(event) -> dict:
        """Build a JSON-serializable dict snapshot from an event ORM object or namespace."""
        fields = [
            "id", "user_id", "title", "description", "start_time", "end_time",
            "location_name", "location_address", "location_coords", "location_lat", "location_lng",
            "event_type", "source", "is_fixed",
            "buffer_before", "buffer_after", "travel_mode", "travel_duration_minutes",
            "departure_time", "status", "linked_task_id", "external_event_id",
            "external_calendar_id", "external_etag", "sync_status", "last_synced_at",
        ]
        snapshot = {}
        for field in fields:
            val = getattr(event, field, None)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            snapshot[field] = val
        return snapshot

    async def detect_conflicts(
        self,
        *,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        buffer_before: int = 0,
        buffer_after: int = 0,
        exclude_event_id: int | None = None,
    ) -> list[EventRead]:
        """Detect event conflicts, accounting for buffer windows on both sides."""
        all_events = await self.repository.list_events(user_id=user_id)
        new_effective_start = start_time - timedelta(minutes=buffer_before)
        new_effective_end = end_time + timedelta(minutes=buffer_after)

        conflicts: list[EventRead] = []
        for event in all_events:
            if exclude_event_id is not None and event.id == exclude_event_id:
                continue
            if event.start_time is None or event.end_time is None:
                continue

            existing_effective_start = event.start_time - timedelta(minutes=(event.buffer_before or 0))
            existing_effective_end = event.end_time + timedelta(minutes=(event.buffer_after or 0))

            if new_effective_start < existing_effective_end and new_effective_end > existing_effective_start:
                conflicts.append(EventRead.model_validate(event))

        return conflicts

    async def find_alternative_slots(
        self,
        *,
        user_id: str,
        duration_minutes: int,
        preferred_date: date | None = None,
        buffer_before: int = 0,
        buffer_after: int = 0,
        max_results: int = 3,
    ) -> list[dict[str, str]]:
        """Find alternative free slots that can accommodate an event and its buffers."""
        from app.services.suggestions import SuggestionService

        suggestion_service = SuggestionService()
        profile = await self.profile_repository.get_profile(user_id)
        events = await self.repository.list_events(user_id=user_id)

        if preferred_date is not None:
            target_dates = [preferred_date]
        else:
            today = datetime.now().date()
            target_dates = [today + timedelta(days=offset) for offset in range(0, 3)]

        total_needed = duration_minutes + buffer_before + buffer_after
        alternatives: list[dict[str, str]] = []
        for target_date in target_dates:
            gaps = suggestion_service._compute_gaps_for_date(
                events=events,
                profile=profile,
                target_date=target_date,
            )
            for gap_start, gap_end in gaps:
                gap_minutes = int((gap_end - gap_start).total_seconds() // 60)
                if gap_minutes < total_needed:
                    continue

                slot_start = gap_start + timedelta(minutes=buffer_before)
                slot_end = slot_start + timedelta(minutes=duration_minutes)
                alternatives.append(
                    {
                        "start_time": slot_start.isoformat(),
                        "end_time": slot_end.isoformat(),
                    }
                )
                if len(alternatives) >= max_results:
                    return alternatives

        return alternatives

    async def create_event(self, user_id: str, payload: EventCreate) -> EventRead:
        data = await self._enrich_event_payload(user_id=user_id, payload=payload.model_dump())
        conflict_events: list[EventRead] = []
        if data.get("start_time") is not None and data.get("end_time") is not None:
            start_dt = data["start_time"] if isinstance(data["start_time"], datetime) else datetime.fromisoformat(str(data["start_time"]))
            end_dt = data["end_time"] if isinstance(data["end_time"], datetime) else datetime.fromisoformat(str(data["end_time"]))
            conflict_events = await self.detect_conflicts(
                user_id=user_id,
                start_time=start_dt,
                end_time=end_dt,
                buffer_before=data.get("buffer_before") or 0,
                buffer_after=data.get("buffer_after") or 0,
            )
        event = await self.repository.create_event({"user_id": user_id, **data})
        synced_event = await self.google_calendar_service.sync_event(user_id=user_id, event_id=event.id)
        if synced_event.linked_task_id is not None:
            await self.task_service.sync_task_schedule_state(user_id=user_id, task_id=synced_event.linked_task_id)
        log_snapshot = self._event_snapshot(synced_event)
        if conflict_events:
            log_snapshot["conflicts"] = [
                {
                    "id": item.id,
                    "title": item.title,
                    "start_time": item.start_time.isoformat() if item.start_time else None,
                    "end_time": item.end_time.isoformat() if item.end_time else None,
                }
                for item in conflict_events
            ]
        await self.repository.write_change_log(
            user_id=user_id,
            event_id=synced_event.id,
            change_type="created",
            new_value_json=log_snapshot,
            trigger_source="user",
        )
        return synced_event

    async def get_event(self, user_id: str, event_id: int) -> EventRead:
        event = await self.repository.get_event(event_id, user_id=user_id)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
        return EventRead.model_validate(event)

    async def update_event(self, user_id: str, event_id: int, payload: EventUpdate) -> EventRead:
        existing = await self.repository.get_event(event_id, user_id=user_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
        previous_status = existing.status
        old_snapshot = self._event_snapshot(existing)

        merged = {
            "title": existing.title,
            "description": existing.description,
            "start_time": existing.start_time,
            "end_time": existing.end_time,
            "location_name": existing.location_name,
            "location_coords": existing.location_coords,
            "event_type": existing.event_type,
            "source": existing.source,
            "is_fixed": existing.is_fixed,
            "buffer_before": existing.buffer_before,
            "buffer_after": existing.buffer_after,
            "travel_mode": existing.travel_mode,
            "travel_duration_minutes": existing.travel_duration_minutes,
            "departure_time": existing.departure_time,
            "status": existing.status,
            "linked_task_id": existing.linked_task_id,
            "external_event_id": existing.external_event_id,
            "external_calendar_id": existing.external_calendar_id,
            "external_etag": existing.external_etag,
            "sync_status": existing.sync_status,
            "last_synced_at": existing.last_synced_at,
        }
        merged.update(payload.model_dump(exclude_none=True))
        merged = await self._enrich_event_payload(user_id=user_id, payload=merged)
        conflict_events: list[EventRead] = []
        if merged.get("start_time") is not None and merged.get("end_time") is not None:
            start_dt = merged["start_time"] if isinstance(merged["start_time"], datetime) else datetime.fromisoformat(str(merged["start_time"]))
            end_dt = merged["end_time"] if isinstance(merged["end_time"], datetime) else datetime.fromisoformat(str(merged["end_time"]))
            conflict_events = await self.detect_conflicts(
                user_id=user_id,
                start_time=start_dt,
                end_time=end_dt,
                buffer_before=merged.get("buffer_before") or 0,
                buffer_after=merged.get("buffer_after") or 0,
                exclude_event_id=event_id,
            )

        event = await self.repository.update_event(
            event_id,
            user_id=user_id,
            payload=merged,
        )
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
        synced_event = await self.google_calendar_service.sync_event(user_id=user_id, event_id=event.id)
        if synced_event.linked_task_id is not None:
            task_read = await self.task_service.sync_task_schedule_state(user_id=user_id, task_id=synced_event.linked_task_id)
            await self._maybe_create_task_progress_reminder(
                user_id=user_id,
                event=synced_event,
                previous_status=previous_status,
                task_read=task_read,
            )
        new_snapshot = self._event_snapshot(synced_event)
        if conflict_events:
            new_snapshot["conflicts"] = [
                {
                    "id": item.id,
                    "title": item.title,
                    "start_time": item.start_time.isoformat() if item.start_time else None,
                    "end_time": item.end_time.isoformat() if item.end_time else None,
                }
                for item in conflict_events
            ]
        await self.repository.write_change_log(
            user_id=user_id,
            event_id=synced_event.id,
            change_type="updated",
            old_value_json=old_snapshot,
            new_value_json=new_snapshot,
            trigger_source="user",
        )
        return synced_event

    async def delete_event(self, user_id: str, event_id: int) -> None:
        existing = await self.repository.get_event(event_id, user_id=user_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
        old_snapshot = self._event_snapshot(existing)
        await self.google_calendar_service.delete_event_mirror(
            user_id=user_id,
            external_event_id=existing.external_event_id,
            source=existing.source,
        )
        linked_task_id = existing.linked_task_id
        deleted = await self.repository.delete_event(event_id, user_id=user_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
        await self.repository.write_change_log(
            user_id=user_id,
            event_id=None,
            change_type="deleted",
            old_value_json=old_snapshot,
            trigger_source="user",
        )
        if linked_task_id is not None:
            await self.task_service.sync_task_schedule_state(user_id=user_id, task_id=linked_task_id)

    async def _enrich_event_payload(self, *, user_id: str, payload: dict) -> dict:
        start_time = payload.get("start_time")
        location_name = payload.get("location_name")
        if not start_time or not location_name:
            return payload

        profile = await self.profile_repository.get_profile(user_id)
        origin = profile.home_location_coords or profile.home_location_name or profile.work_location_coords or profile.work_location_name
        destination = payload.get("location_coords")
        enriched = dict(payload)
        if destination is None:
            try:
                geocoded = await self.context_service.geocode(location_name)
                destination = geocoded.location
                enriched["location_coords"] = geocoded.location
                enriched["location_address"] = geocoded.formatted_address
                if geocoded.location and "," in geocoded.location:
                    lng, lat = geocoded.location.split(",", 1)
                    enriched["location_lat"] = float(lat)
                    enriched["location_lng"] = float(lng)
            except Exception:
                destination = location_name
        if not origin or not destination:
            return payload

        try:
            travel = await self.context_service.estimate_travel(
                origin=origin,
                destination=destination,
                mode=profile.transport_preference or "driving",
            )
        except Exception:
            return payload

        start_dt = start_time if isinstance(start_time, datetime) else datetime.fromisoformat(str(start_time))
        departure_dt = start_dt - timedelta(seconds=travel.duration_seconds)
        enriched["travel_mode"] = travel.mode
        enriched["travel_duration_minutes"] = int(round(travel.duration_minutes))
        enriched["departure_time"] = departure_dt
        return enriched

    async def _maybe_create_task_progress_reminder(self, *, user_id: str, event, previous_status: str | None, task_read) -> None:
        if event.event_type != "focus_block" or event.linked_task_id is None or task_read is None:
            return
        if previous_status == event.status:
            return

        remind_type = None
        message = None
        now = datetime.now(timezone.utc)
        if event.status == "completed":
            remind_type = "task_progress"
            message = (
                f"Task progress updated: {task_read.content} is now {task_read.completed_minutes} / "
                f"{task_read.estimated_duration_minutes or task_read.completed_minutes} minutes complete."
            )
        elif event.status == "canceled" and (task_read.remaining_minutes or 0) > 0:
            remind_type = "task_replan"
            message = (
                f"Task replan needed: {task_read.content} still has {task_read.remaining_minutes} minutes remaining. "
                "Check the latest suggestions for replacement focus blocks."
            )

        if remind_type and message:
            await self.reminder_repository.create_reminder(
                {
                    "user_id": user_id,
                    "target_type": "task",
                    "target_id": task_read.id,
                    "remind_type": remind_type,
                    "remind_at": now,
                    "delivery_channel": "in_app",
                    "message": message,
                    "status": "pending",
                }
            )
