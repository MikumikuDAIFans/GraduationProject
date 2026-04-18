"""Gemini API helper for assistant replies and actions."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import httpx
from loguru import logger

from app.core.config import get_settings
from app.core.error_handler import GeminiAPIError


class GeminiClient:
    """Minimal async Gemini REST client."""

    _consecutive_failures = 0
    _circuit_open_until: datetime | None = None

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.llm_provider == "gemini" and bool(self.settings.gemini_api_key)

    @classmethod
    def health_status(cls, *, enabled: bool, provider: str) -> dict[str, Any]:
        return {
            "enabled": enabled,
            "provider": provider,
            "circuit_open": cls._is_circuit_open(),
            "circuit_open_until": cls._circuit_open_until.isoformat() if cls._circuit_open_until else None,
            "consecutive_failures": cls._consecutive_failures,
        }

    async def generate_plan(
        self,
        *,
        user_message: str,
        history: list[dict[str, Any]],
        events: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
        external_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Gemini is not configured.")

        prompt = self._build_plan_prompt(
            user_message=user_message,
            history=history,
            events=events,
            tasks=tasks,
            profile=profile,
            external_context=external_context,
        )
        text = await self._generate_text(prompt)
        return self._parse_json_payload(text)

    async def generate_reply(
        self,
        *,
        user_message: str,
        history: list[dict[str, Any]],
        events: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
        external_context: dict[str, Any] | None = None,
    ) -> str:
        if not self.enabled:
            raise RuntimeError("Gemini is not configured.")
        prompt = self._build_reply_prompt(
            user_message=user_message,
            history=history,
            events=events,
            tasks=tasks,
            profile=profile,
            external_context=external_context,
        )
        return await self._generate_text(prompt)

    async def generate_text(self, prompt: str) -> str:
        """Public text generation helper for workflow / ReAct callers."""
        if not self.enabled:
            raise RuntimeError("Gemini is not configured.")
        return await self._generate_text(prompt)

    async def generate_plan_stream(
        self,
        *,
        user_message: str,
        history: list[dict[str, Any]],
        events: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        profile: dict[str, Any] | None = None,
        external_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream text chunks from Gemini's SSE endpoint."""
        if not self.enabled:
            raise RuntimeError("Gemini is not configured.")

        prompt = self._build_plan_prompt(
            user_message=user_message,
            history=history,
            events=events,
            tasks=tasks,
            profile=profile,
            external_context=external_context,
        )
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"{self.settings.gemini_model}:streamGenerateContent"
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                url,
                params={"key": self.settings.gemini_api_key, "alt": "sse"},
                json={
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt},
                            ]
                        }
                    ]
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    candidates = chunk.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        text = part.get("text")
                        if text:
                            yield text

    async def _generate_text(self, prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"{self.settings.gemini_model}:generateContent"
        )

        data = await self._post_with_retry(
            url=url,
            payload={
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                        ]
                    }
                ]
            },
        )

        candidates = data.get("candidates") or []
        if not candidates:
            raise GeminiAPIError("Gemini returned no candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts if part.get("text"))
        if not text.strip():
            raise GeminiAPIError("Gemini returned an empty reply.")
        return text.strip()

    async def _post_with_retry(self, *, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        timeout = httpx.Timeout(self.settings.gemini_timeout_seconds)
        if self._is_circuit_open():
            raise GeminiAPIError(
                "AI 服务正在短暂恢复中，请稍后再试。",
                details={"circuit_open_until": self._circuit_open_until.isoformat() if self._circuit_open_until else None},
            )
        for attempt in range(1, self.settings.gemini_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        url,
                        params={"key": self.settings.gemini_api_key},
                        json=payload,
                    )
                    response.raise_for_status()
                    self._record_success()
                    return response.json()
            except (httpx.TimeoutException, httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                self._record_failure()
                if attempt >= self.settings.gemini_max_retries:
                    break
                logger.bind(component="gemini").warning(
                    "Gemini request failed on attempt {attempt}/{max_retries}: {error}",
                    attempt=attempt,
                    max_retries=self.settings.gemini_max_retries,
                    error=str(exc),
                )
                await asyncio.sleep(self.settings.gemini_retry_delay_seconds * attempt)

        raise GeminiAPIError(
            f"AI 服务暂时不可用，已重试 {self.settings.gemini_max_retries} 次。",
            details={"last_error": str(last_error) if last_error else "unknown"},
        )

    @classmethod
    def _record_success(cls) -> None:
        cls._consecutive_failures = 0
        cls._circuit_open_until = None

    def _record_failure(self) -> None:
        self.__class__._consecutive_failures += 1
        if self.__class__._consecutive_failures >= self.settings.gemini_max_retries:
            self.__class__._circuit_open_until = datetime.now(timezone.utc) + timedelta(
                seconds=self.settings.gemini_circuit_breaker_seconds,
            )

    @classmethod
    def _is_circuit_open(cls) -> bool:
        if cls._circuit_open_until is None:
            return False
        if datetime.now(timezone.utc) >= cls._circuit_open_until:
            cls._circuit_open_until = None
            cls._consecutive_failures = 0
            return False
        return True

    def _build_plan_prompt(
        self,
        *,
        user_message: str,
        history: list[dict[str, Any]],
        events: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        profile: dict[str, Any] | None,
        external_context: dict[str, Any] | None,
    ) -> str:
        now = datetime.now().isoformat(timespec="minutes")
        history_lines = "\n".join(
            f"- {item['role']}: {item['content']}" for item in history[-6:]
        ) or "- no prior messages"
        event_lines = "\n".join(
            (
                f"- {item.get('title', 'Untitled')} | "
                f"start={item.get('start_time')} | end={item.get('end_time')} | "
                f"location={item.get('location_name')}"
            )
            for item in events[:8]
        ) or "- no events"
        task_lines = "\n".join(
            (
                f"- {item.get('content')} | status={item.get('status')} | "
                f"deadline={item.get('deadline')} | priority={item.get('priority')}"
            )
            for item in tasks[:8]
        ) or "- no tasks"
        profile_lines = "\n".join(
            f"- {key}: {value}" for key, value in (profile or {}).items() if value not in (None, "", {})
        ) or "- no profile context"
        external_lines = "\n".join(
            f"- {key}: {value}" for key, value in (external_context or {}).items() if value not in (None, "", {})
        ) or "- no external context"

        return f"""
You are the backend assistant for a personal affairs planner (个人事务助理).
Analyze the user message and decide whether there is a clear write action to perform.

## OUTPUT FORMAT
Reply with JSON only — no markdown fences, no extra text.
Use the same language as the user for the "reply" field (Chinese if user writes Chinese).

## ACTION RULES
- Allowed action types: "create_event", "create_task"
- Only emit actions when user intent is EXPLICIT and COMPLETE (clear title + time for events, clear content for tasks)
- If time is ambiguous or missing: do NOT create anything. Propose a clarifying question instead.
- If information is partially missing, ask exactly one concise clarification question.
- Do not create duplicate items already visible in the events/tasks list.
- When creating an event: provide ISO 8601 datetimes (YYYY-MM-DDTHH:MM:SS) or null.
- When creating a task: provide content + optional deadline (ISO 8601 date) + optional priority (1-5).

## REPLY STYLE (for "reply" field)
- Be concise and action-oriented (2–5 sentences max).
- Prefer clean Markdown bullets over raw JSON fragments in the reply field.
- If planning time blocks: always include specific time slots in HH:MM–HH:MM format.
- If suggesting a schedule: list each item as a bullet with time + activity.
- If the user asks "how to plan X": give a concrete step-by-step with durations.
- Never say "I cannot do that" when you could propose a plan instead.

Current time: {now}
User timezone: {self.settings.app_timezone}

Recent conversation:
{history_lines}

Upcoming events:
{event_lines}

Current tasks:
{task_lines}

Profile:
{profile_lines}

External context:
{external_lines}

User message:
{user_message}

JSON schema:
{{
  "reply": "concise natural-language reply with time slots if planning",
  "actions": [
    {{
      "type": "create_event" | "create_task",
      "payload": {{}}
    }}
  ]
}}
""".strip()

    def _build_reply_prompt(
        self,
        *,
        user_message: str,
        history: list[dict[str, Any]],
        events: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        profile: dict[str, Any] | None,
        external_context: dict[str, Any] | None,
    ) -> str:
        now = datetime.now().isoformat(timespec="minutes")
        history_lines = "\n".join(
            f"- {item['role']}: {item['content']}" for item in history[-6:]
        ) or "- no prior messages"
        event_lines = "\n".join(
            (
                f"- {item.get('title', 'Untitled')} | "
                f"start={item.get('start_time')} | end={item.get('end_time')} | "
                f"location={item.get('location_name')}"
            )
            for item in events[:8]
        ) or "- no events"
        task_lines = "\n".join(
            (
                f"- {item.get('content')} | status={item.get('status')} | "
                f"deadline={item.get('deadline')} | priority={item.get('priority')}"
            )
            for item in tasks[:8]
        ) or "- no tasks"
        profile_lines = "\n".join(
            f"- {key}: {value}" for key, value in (profile or {}).items() if value not in (None, "", {})
        ) or "- no profile context"
        external_lines = "\n".join(
            f"- {key}: {value}" for key, value in (external_context or {}).items() if value not in (None, "", {})
        ) or "- no external context"

        return f"""
You are a personal affairs assistant (个人事务助理).
Reply in the same language as the user (Chinese if user writes Chinese).
Be concise, practical, and action-oriented.

## REPLY GUIDELINES
- Answer directly without preamble.
- When planning time: always specify exact time slots (HH:MM–HH:MM).
- When listing steps: use numbered bullets with durations.
- When referencing tasks/events: use their exact names from the context below.
- Do not claim that a calendar item was created unless it actually happened.
- Limit reply to 6 sentences or bullet points maximum.

Current time: {now}
User timezone: {self.settings.app_timezone}

Recent conversation:
{history_lines}

Upcoming events:
{event_lines}

Current tasks:
{task_lines}

Profile:
{profile_lines}

External context:
{external_lines}

User message:
{user_message}
""".strip()

    def _parse_json_payload(self, text: str) -> dict[str, Any]:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            candidate = candidate.replace("json", "", 1).strip()
        return json.loads(candidate)
