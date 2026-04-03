"""Google Calendar one-way mirror sync service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.api.schemas import (
    EventRead,
    GoogleCalendarAuthCallbackRead,
    GoogleCalendarAuthStartRead,
    GoogleCalendarStatusRead,
    GoogleCalendarSyncRead,
)
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.repositories.events import EventRepository
from app.repositories.profiles import UserProfileRepository
from app.tools.google_calendar import GoogleCalendarClient, GoogleCalendarError


class GoogleCalendarService:
    """Manage Google Calendar OAuth state and one-way mirror sync."""

    def __init__(self) -> None:
        self.settings = get_settings()
        session_factory = get_sessionmaker()
        self.profile_repository = UserProfileRepository(session_factory)
        self.event_repository = EventRepository(session_factory)
        self.client = GoogleCalendarClient()

    async def get_status(self, user_id: str) -> GoogleCalendarStatusRead:
        profile = await self.profile_repository.get_profile(user_id)
        auth_url = None
        if self.settings.google_calendar_enabled and not profile.google_calendar_tokens_json:
            try:
                auth_url, _ = self.client.get_authorization_url()
            except Exception:
                auth_url = None

        return GoogleCalendarStatusRead(
            enabled=self.settings.google_calendar_enabled,
            status=profile.google_calendar_status,
            connected=bool(profile.google_calendar_tokens_json),
            calendar_id=self.settings.google_calendar_id,
            redirect_uri=self.settings.google_redirect_uri,
            connected_at=profile.google_calendar_connected_at,
            last_sync_at=profile.google_calendar_last_sync_at,
            last_error=profile.google_calendar_error,
            has_refresh_token=bool((profile.google_calendar_tokens_json or {}).get("refresh_token")),
            auth_url=auth_url,
        )

    async def start_auth(self, user_id: str) -> GoogleCalendarAuthStartRead:
        self._ensure_enabled()
        auth_url, state = self.client.get_authorization_url()

        profile = await self.profile_repository.get_profile(user_id)
        preferences = dict(profile.preferences_json or {})
        preferences["google_calendar_oauth_state"] = state
        await self.profile_repository.update_profile(user_id, {"preferences_json": preferences})

        return GoogleCalendarAuthStartRead(auth_url=auth_url, state=state)

    async def complete_auth(self, user_id: str, *, code: str, state: str | None) -> GoogleCalendarAuthCallbackRead:
        self._ensure_enabled()
        profile = await self.profile_repository.get_profile(user_id)
        expected_state = (profile.preferences_json or {}).get("google_calendar_oauth_state")
        if expected_state and state and expected_state != state:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="google oauth state mismatch")

        tokens_json = self.client.exchange_code(code=code)
        connected_at = datetime.now(UTC)
        preferences = dict(profile.preferences_json or {})
        preferences.pop("google_calendar_oauth_state", None)
        await self.profile_repository.update_profile(
            user_id,
            {
                "preferences_json": preferences or None,
                "google_calendar_tokens_json": tokens_json,
                "google_calendar_status": "connected",
                "google_calendar_connected_at": connected_at,
                "google_calendar_error": None,
            },
        )

        return GoogleCalendarAuthCallbackRead(
            status="connected",
            connected=True,
            calendar_id=self.settings.google_calendar_id,
            connected_at=connected_at,
        )

    async def sync(
        self,
        user_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> GoogleCalendarSyncRead:
        self._ensure_enabled()
        profile = await self.profile_repository.get_profile(user_id)
        tokens_json = profile.google_calendar_tokens_json
        if not tokens_json:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="google calendar is not connected")

        range_start = self._ensure_aware(start or datetime.now(UTC) - timedelta(days=7))
        range_end = self._ensure_aware(end or datetime.now(UTC) + timedelta(days=30))
        now = datetime.now(UTC)

        pushed = 0
        imported = 0
        updated = 0
        skipped = 0
        details: list[str] = []

        local_events = await self.event_repository.list_events(user_id=user_id, limit=500)
        for event in local_events:
            if event.source == "google_imported":
                continue
            if event.start_time is None or event.end_time is None:
                skipped += 1
                continue
            if event.end_time < range_start or event.start_time > range_end:
                continue

            try:
                remote_event, tokens_json, mode = await self._upsert_remote_event(
                    tokens_json=tokens_json,
                    event=event,
                )
            except Exception as exc:
                await self.event_repository.update_event(
                    event.id,
                    user_id=user_id,
                    payload={"sync_status": "sync_error"},
                )
                details.append(f"push failed for local event #{event.id}: {exc}")
                continue

            await self.event_repository.update_event(
                event.id,
                user_id=user_id,
                payload={
                    "external_event_id": remote_event.get("id"),
                    "external_calendar_id": self.settings.google_calendar_id,
                    "external_etag": remote_event.get("etag"),
                    "sync_status": "synced",
                    "last_synced_at": now,
                },
            )
            if mode == "created":
                pushed += 1
            else:
                updated += 1

        remote_events, tokens_json = await self.client.list_events(
            tokens_json=tokens_json,
            calendar_id=self.settings.google_calendar_id,
            time_min=range_start,
            time_max=range_end,
        )
        for remote_event in remote_events:
            remote_id = remote_event.get("id")
            if not remote_id:
                skipped += 1
                continue
            local_event = await self.event_repository.get_by_external_event_id(
                user_id=user_id,
                external_event_id=remote_id,
            )
            parsed = self.client.parse_remote_event(remote_event)
            parsed["sync_status"] = "imported"
            parsed["last_synced_at"] = now

            if local_event is None:
                await self.event_repository.create_event({"user_id": user_id, **parsed})
                imported += 1
                continue

            if local_event.source == "google_imported":
                await self.event_repository.update_event(
                    local_event.id,
                    user_id=user_id,
                    payload=parsed,
                )
                updated += 1
            else:
                skipped += 1

        await self.profile_repository.update_profile(
            user_id,
            {
                "google_calendar_tokens_json": tokens_json,
                "google_calendar_status": "synced",
                "google_calendar_last_sync_at": now,
                "google_calendar_error": None,
            },
        )

        return GoogleCalendarSyncRead(
            status="ok",
            pushed=pushed,
            imported=imported,
            updated=updated,
            skipped=skipped,
            last_sync_at=now,
            details=details,
        )

    async def sync_event(self, *, user_id: str, event_id: int) -> EventRead:
        event = await self.event_repository.get_event(event_id, user_id=user_id)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")

        if event.source == "google_imported":
            return EventRead.model_validate(event)

        if not self.settings.google_calendar_enabled:
            return EventRead.model_validate(event)

        profile = await self.profile_repository.get_profile(user_id)
        if not profile.google_calendar_tokens_json:
            return EventRead.model_validate(event)

        if event.start_time is None or event.end_time is None:
            updated = await self.event_repository.update_event(
                event.id,
                user_id=user_id,
                payload={"sync_status": "local_only"},
            )
            return EventRead.model_validate(updated or event)

        try:
            remote_event, tokens_json, _ = await self._upsert_remote_event(
                tokens_json=profile.google_calendar_tokens_json,
                event=event,
            )
            now = datetime.now(UTC)
            await self.profile_repository.update_profile(
                user_id,
                {
                    "google_calendar_tokens_json": tokens_json,
                    "google_calendar_status": "connected",
                    "google_calendar_error": None,
                },
            )
            updated = await self.event_repository.update_event(
                event.id,
                user_id=user_id,
                payload={
                    "external_event_id": remote_event.get("id"),
                    "external_calendar_id": self.settings.google_calendar_id,
                    "external_etag": remote_event.get("etag"),
                    "sync_status": "synced",
                    "last_synced_at": now,
                },
            )
            return EventRead.model_validate(updated or event)
        except Exception as exc:
            await self.profile_repository.update_profile(
                user_id,
                {
                    "google_calendar_status": "error",
                    "google_calendar_error": str(exc),
                },
            )
            updated = await self.event_repository.update_event(
                event.id,
                user_id=user_id,
                payload={"sync_status": "sync_error"},
            )
            return EventRead.model_validate(updated or event)

    async def delete_event_mirror(self, *, user_id: str, external_event_id: str | None, source: str | None) -> None:
        if not external_event_id or source == "google_imported" or not self.settings.google_calendar_enabled:
            return

        profile = await self.profile_repository.get_profile(user_id)
        if not profile.google_calendar_tokens_json:
            return

        try:
            tokens_json = await self.client.delete_event(
                tokens_json=profile.google_calendar_tokens_json,
                calendar_id=self.settings.google_calendar_id,
                event_id=external_event_id,
            )
            await self.profile_repository.update_profile(
                user_id,
                {
                    "google_calendar_tokens_json": tokens_json,
                    "google_calendar_error": None,
                },
            )
        except Exception as exc:
            await self.profile_repository.update_profile(
                user_id,
                {
                    "google_calendar_status": "error",
                    "google_calendar_error": str(exc),
                },
            )

    async def _upsert_remote_event(self, *, tokens_json: dict[str, Any], event) -> tuple[dict[str, Any], dict[str, Any], str]:
        payload = self.client.build_event_payload(event=event)
        if event.external_event_id:
            remote_event, refreshed_tokens = await self.client.update_event(
                tokens_json=tokens_json,
                calendar_id=self.settings.google_calendar_id,
                event_id=event.external_event_id,
                payload=payload,
            )
            return remote_event, refreshed_tokens, "updated"

        remote_event, refreshed_tokens = await self.client.create_event(
            tokens_json=tokens_json,
            calendar_id=self.settings.google_calendar_id,
            payload=payload,
        )
        return remote_event, refreshed_tokens, "created"

    def _ensure_enabled(self) -> None:
        if not self.settings.google_calendar_enabled:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="google calendar sync is disabled")

    def _ensure_aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
