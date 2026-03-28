"""Gemini API helper for assistant replies and actions."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx

from app.core.config import get_settings


class GeminiClient:
    """Minimal async Gemini REST client."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.llm_provider == "gemini" and bool(self.settings.gemini_api_key)

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

    async def _generate_text(self, prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"{self.settings.gemini_model}:generateContent"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                params={"key": self.settings.gemini_api_key},
                json={
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt},
                            ]
                        }
                    ]
                },
            )
            response.raise_for_status()
            data = response.json()

        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts if part.get("text"))
        if not text.strip():
            raise RuntimeError("Gemini returned an empty reply.")
        return text.strip()

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
- Do not create duplicate items already visible in the events/tasks list.
- When creating an event: provide ISO 8601 datetimes (YYYY-MM-DDTHH:MM:SS) or null.
- When creating a task: provide content + optional deadline (ISO 8601 date) + optional priority (1-5).

## REPLY STYLE (for "reply" field)
- Be concise and action-oriented (2–5 sentences max).
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
