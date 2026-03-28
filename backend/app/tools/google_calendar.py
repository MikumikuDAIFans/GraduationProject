"""Google Calendar OAuth and event operations."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR, get_settings


SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarError(RuntimeError):
    """Raised when Google Calendar integration cannot complete."""


class GoogleCalendarClient:
    """Thin wrapper around Google Calendar OAuth and event APIs."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def get_authorization_url(self) -> tuple[str, str]:
        flow = self._build_flow()
        state = secrets.token_urlsafe(24)
        auth_url, returned_state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url, returned_state

    def exchange_code(self, *, code: str) -> dict[str, Any]:
        flow = self._build_flow()
        flow.fetch_token(code=code)
        if flow.credentials is None:
            raise GoogleCalendarError("google oauth completed without credentials")
        return self._credentials_to_dict(flow.credentials)

    def list_events(
        self,
        *,
        tokens_json: dict[str, Any],
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        service, refreshed_tokens = self._build_service(tokens_json)
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=self._rfc3339(time_min),
                timeMax=self._rfc3339(time_max),
                maxResults=250,
                singleEvents=True,
                showDeleted=False,
                orderBy="startTime",
            )
            .execute()
        )
        return response.get("items", []), refreshed_tokens

    def create_event(
        self,
        *,
        tokens_json: dict[str, Any],
        calendar_id: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        service, refreshed_tokens = self._build_service(tokens_json)
        created = service.events().insert(calendarId=calendar_id, body=payload).execute()
        return created, refreshed_tokens

    def update_event(
        self,
        *,
        tokens_json: dict[str, Any],
        calendar_id: str,
        event_id: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        service, refreshed_tokens = self._build_service(tokens_json)
        updated = (
            service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=payload)
            .execute()
        )
        return updated, refreshed_tokens

    def delete_event(
        self,
        *,
        tokens_json: dict[str, Any],
        calendar_id: str,
        event_id: str,
    ) -> dict[str, Any]:
        service, refreshed_tokens = self._build_service(tokens_json)
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return refreshed_tokens

    def build_event_payload(self, *, event) -> dict[str, Any]:
        if event.start_time is None or event.end_time is None:
            raise GoogleCalendarError("event must have both start_time and end_time to sync")

        return {
            "summary": event.title,
            "description": event.description or "",
            "location": event.location_name or "",
            "start": self._build_time_payload(event.start_time),
            "end": self._build_time_payload(event.end_time),
        }

    def parse_remote_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        start_payload = payload.get("start") or {}
        end_payload = payload.get("end") or {}
        return {
            "title": payload.get("summary") or "(No title)",
            "description": payload.get("description"),
            "location_name": payload.get("location"),
            "start_time": self._parse_google_time(start_payload),
            "end_time": self._parse_google_time(end_payload),
            "status": "planned",
            "source": "google_imported",
            "external_event_id": payload.get("id"),
            "external_calendar_id": self.settings.google_calendar_id,
            "external_etag": payload.get("etag"),
        }

    def _build_flow(self):
        self._ensure_google_deps()
        from google_auth_oauthlib.flow import Flow

        client_config = self._load_client_config()
        flow = Flow.from_client_config(client_config, scopes=SCOPES)
        redirect_uri = self.settings.google_redirect_uri
        if redirect_uri:
            flow.redirect_uri = redirect_uri
        return flow

    def _build_service(self, tokens_json: dict[str, Any]):
        self._ensure_google_deps()
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials.from_authorized_user_info(tokens_json, scopes=SCOPES)
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                raise GoogleCalendarError("google calendar credentials are missing or expired")
        return build("calendar", "v3", credentials=credentials), self._credentials_to_dict(credentials)

    def _load_client_config(self) -> dict[str, Any]:
        json_path = self.settings.google_client_secret_json_path
        if json_path:
            resolved_path = Path(json_path)
            if not resolved_path.is_absolute():
                resolved_path = (BASE_DIR / resolved_path).resolve()
            if resolved_path.exists():
                return json.loads(resolved_path.read_text(encoding="utf-8"))

        if self.settings.google_client_id and self.settings.google_client_secret and self.settings.google_redirect_uri:
            return {
                "web": {
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.settings.google_redirect_uri],
                }
            }

        raise GoogleCalendarError("google client credentials are not configured")

    def _credentials_to_dict(self, credentials) -> dict[str, Any]:
        expiry = getattr(credentials, "expiry", None)
        return {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes or []),
            "expiry": expiry.isoformat() if expiry else None,
        }

    def _build_time_payload(self, value: datetime) -> dict[str, str]:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        timezone_name = value.tzinfo.tzname(value) or "UTC"
        return {"dateTime": value.isoformat(), "timeZone": timezone_name}

    def _parse_google_time(self, payload: dict[str, Any]) -> datetime | None:
        raw_datetime = payload.get("dateTime")
        if raw_datetime:
            return datetime.fromisoformat(raw_datetime.replace("Z", "+00:00"))

        raw_date = payload.get("date")
        if raw_date:
            return datetime.fromisoformat(f"{raw_date}T00:00:00+00:00")
        return None

    def _rfc3339(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()

    def _ensure_google_deps(self) -> None:
        try:
            import google.auth.transport.requests  # noqa: F401
            import google.oauth2.credentials  # noqa: F401
            import google_auth_oauthlib.flow  # noqa: F401
            import googleapiclient.discovery  # noqa: F401
        except ImportError as exc:
            raise GoogleCalendarError(
                "google calendar dependencies are missing; install backend requirements first"
            ) from exc
