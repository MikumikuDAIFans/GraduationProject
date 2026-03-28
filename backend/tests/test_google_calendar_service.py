from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.google_calendar import GoogleCalendarService


class FakeProfileRepository:
    def __init__(self) -> None:
        self.profile = SimpleNamespace(
            preferences_json={"focus_block_minutes": 60},
            google_calendar_tokens_json={"refresh_token": "refresh-token"},
            google_calendar_status="disconnected",
            google_calendar_connected_at=None,
            google_calendar_last_sync_at=None,
            google_calendar_error=None,
        )

    async def get_profile(self, user_id: str):
        return self.profile

    async def update_profile(self, user_id: str, payload: dict):
        for key, value in payload.items():
            setattr(self.profile, key, value)
        return self.profile


class FakeEventRepository:
    def __init__(self) -> None:
        self.items = {
            1: SimpleNamespace(
                id=1,
                user_id="local-user",
                title="Local defense rehearsal",
                description="sync outward",
                start_time=datetime(2026, 3, 28, 9, 0, tzinfo=UTC),
                end_time=datetime(2026, 3, 28, 10, 0, tzinfo=UTC),
                location_name="Campus",
                source="local",
                external_event_id=None,
                external_calendar_id=None,
                external_etag=None,
                sync_status="local_only",
                last_synced_at=None,
            )
        }
        self.next_id = 2

    async def list_events(self, *, user_id: str, limit: int = 100, offset: int = 0):
        return list(self.items.values())

    async def get_event(self, event_id: int, *, user_id: str):
        return self.items.get(event_id)

    async def get_by_external_event_id(self, *, user_id: str, external_event_id: str):
        for item in self.items.values():
            if item.external_event_id == external_event_id:
                return item
        return None

    async def update_event(self, event_id: int, *, user_id: str, payload: dict):
        item = self.items[event_id]
        for key, value in payload.items():
            setattr(item, key, value)
        self.items[event_id] = item
        return item

    async def create_event(self, payload: dict):
        item = SimpleNamespace(id=self.next_id, **payload)
        self.items[self.next_id] = item
        self.next_id += 1
        return item


class FakeGoogleCalendarClient:
    def get_authorization_url(self):
        return "https://example.com/google-auth", "oauth-state"

    def exchange_code(self, *, code: str):
        return {"refresh_token": "refresh-token", "token": "access-token"}

    def build_event_payload(self, *, event):
        return {"summary": event.title}

    def create_event(self, *, tokens_json: dict, calendar_id: str, payload: dict):
        return {"id": "remote-local-1", "etag": "etag-created"}, {
            **tokens_json,
            "token": "updated-access-token",
        }

    def update_event(self, *, tokens_json: dict, calendar_id: str, event_id: str, payload: dict):
        return {"id": event_id, "etag": "etag-updated"}, tokens_json

    def list_events(self, *, tokens_json: dict, calendar_id: str, time_min: datetime, time_max: datetime):
        return [
            {"id": "remote-local-1", "etag": "etag-created"},
            {
                "id": "remote-import-1",
                "summary": "Imported advisor meeting",
                "description": "from google",
                "location": "Library",
                "etag": "etag-imported",
                "start": {"dateTime": "2026-03-29T10:00:00+00:00"},
                "end": {"dateTime": "2026-03-29T11:00:00+00:00"},
            },
        ], tokens_json

    def delete_event(self, *, tokens_json: dict, calendar_id: str, event_id: str):
        return tokens_json

    def parse_remote_event(self, payload: dict):
        return {
            "title": payload.get("summary", "(No title)"),
            "description": payload.get("description"),
            "location_name": payload.get("location"),
            "start_time": datetime.fromisoformat(payload["start"]["dateTime"]) if payload.get("start") else None,
            "end_time": datetime.fromisoformat(payload["end"]["dateTime"]) if payload.get("end") else None,
            "status": "planned",
            "source": "google_imported",
            "external_event_id": payload.get("id"),
            "external_calendar_id": "primary",
            "external_etag": payload.get("etag"),
        }


def build_service() -> tuple[GoogleCalendarService, FakeProfileRepository, FakeEventRepository]:
    service = GoogleCalendarService()
    profile_repository = FakeProfileRepository()
    event_repository = FakeEventRepository()
    service.profile_repository = profile_repository
    service.event_repository = event_repository
    service.client = FakeGoogleCalendarClient()
    service.settings.google_calendar_enabled = True
    service.settings.google_calendar_id = "primary"
    return service, profile_repository, event_repository


def test_start_auth_persists_state() -> None:
    service, profile_repository, _ = build_service()

    result = asyncio.run(service.start_auth("local-user"))

    assert result.state == "oauth-state"
    assert profile_repository.profile.preferences_json["google_calendar_oauth_state"] == "oauth-state"


def test_sync_pushes_local_events_and_imports_remote_events() -> None:
    service, profile_repository, event_repository = build_service()

    result = asyncio.run(
        service.sync(
            "local-user",
            start=datetime(2026, 3, 27, 0, 0, tzinfo=UTC),
            end=datetime(2026, 3, 30, 0, 0, tzinfo=UTC),
        )
    )

    local_event = event_repository.items[1]
    imported_event = event_repository.items[2]

    assert result.pushed == 1
    assert result.imported == 1
    assert local_event.external_event_id == "remote-local-1"
    assert local_event.sync_status == "synced"
    assert imported_event.source == "google_imported"
    assert imported_event.external_event_id == "remote-import-1"
    assert profile_repository.profile.google_calendar_status == "synced"
    assert profile_repository.profile.google_calendar_last_sync_at is not None
