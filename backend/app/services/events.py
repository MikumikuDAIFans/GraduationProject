"""Event service layer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
            "location_name", "location_coords", "event_type", "source", "is_fixed",
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

    async def create_event(self, user_id: str, payload: EventCreate) -> EventRead:
        data = await self._enrich_event_payload(user_id=user_id, payload=payload.model_dump())
        event = await self.repository.create_event({"user_id": user_id, **data})
        synced_event = await self.google_calendar_service.sync_event(user_id=user_id, event_id=event.id)
        if synced_event.linked_task_id is not None:
            await self.task_service.sync_task_schedule_state(user_id=user_id, task_id=synced_event.linked_task_id)
        await self.repository.write_change_log(
            user_id=user_id,
            event_id=synced_event.id,
            change_type="created",
            new_value_json=self._event_snapshot(synced_event),
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
        await self.repository.write_change_log(
            user_id=user_id,
            event_id=synced_event.id,
            change_type="updated",
            old_value_json=old_snapshot,
            new_value_json=self._event_snapshot(synced_event),
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
