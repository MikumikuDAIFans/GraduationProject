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
from app.schemas.assistant_understanding import validate_message_understanding_payload


class GeminiClient:
    """Minimal async LLM client.

    The public class name is kept for compatibility with older call sites, but
    generation now uses the configured primary provider first and falls back to
    Gemini when configured.
    """

    _consecutive_failures = 0
    _circuit_open_until: datetime | None = None
    _last_generation_failed_all = False

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return any(self._provider_enabled(provider) for provider in self._provider_order())

    @classmethod
    def health_status(cls, *, enabled: bool, provider: str, fallback_provider: str | None = None) -> dict[str, Any]:
        return {
            "enabled": enabled,
            "provider": provider,
            "fallback_provider": fallback_provider,
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

    async def extract_event_creation_semantics(
        self,
        *,
        user_message: str,
        now: datetime,
        profile: Any | None = None,
        external_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract event creation semantics for the conductor's Understanding specialist."""
        if not self.enabled:
            raise RuntimeError("Gemini is not configured.")
        prompt = self._build_event_semantics_prompt(
            user_message=user_message,
            now=now,
            profile=profile,
            external_context=external_context,
        )
        text = await self._generate_text(prompt)
        payload = self._parse_json_payload(text)
        if not isinstance(payload, dict):
            raise GeminiAPIError("Gemini returned invalid event semantics.")
        return payload

    async def extract_message_understanding(
        self,
        *,
        user_message: str,
        now: datetime,
        profile: Any | None = None,
        external_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract the conductor's top-level semantic understanding before rule fallback."""
        if not self.enabled:
            raise RuntimeError("Gemini is not configured.")
        prompt = self._build_message_understanding_prompt(
            user_message=user_message,
            now=now,
            profile=profile,
            external_context=external_context,
        )
        text = await self._generate_text(prompt)
        payload = self._parse_json_payload(text)
        if not isinstance(payload, dict):
            raise GeminiAPIError("Gemini returned invalid message understanding.")
        try:
            return validate_message_understanding_payload(payload)
        except ValueError as exc:
            raise GeminiAPIError("Gemini returned invalid message understanding.") from exc

    async def generate_text(self, prompt: str) -> str:
        """Public text generation helper for assistant callers."""
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
        if not self._provider_enabled("gemini"):
            raise RuntimeError("Gemini streaming is not configured.")

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
        errors: list[str] = []
        self.__class__._last_generation_failed_all = False
        for provider in self._provider_order():
            if not self._provider_enabled(provider):
                continue
            try:
                if provider == "deepseek":
                    return await self._generate_text_deepseek(prompt)
                if provider == "gemini":
                    return await self._generate_text_gemini(prompt)
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                self.__class__._circuit_open_until = None
                self.__class__._consecutive_failures = 0
                logger.bind(component="llm", provider=provider).warning(
                    "LLM provider failed, trying fallback when available: {error}",
                    error=str(exc),
                )
                continue
        self.__class__._last_generation_failed_all = True
        raise GeminiAPIError(
            "AI 服务暂时不可用，所有已配置模型都调用失败。",
            details={"errors": errors or ["no configured provider"]},
        )

    async def _generate_text_deepseek(self, prompt: str) -> str:
        url = f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"
        data = await self._post_openai_chat_with_retry(
            url=url,
            api_key=self.settings.deepseek_api_key or "",
            model=self.settings.deepseek_model,
            payload={
                "model": self.settings.deepseek_model,
                "messages": [
                    {"role": "system", "content": "你是一个严谨的个人事务助手后端模块。请严格按调用方要求输出。"},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout_seconds=self.settings.deepseek_timeout_seconds,
            max_retries=self.settings.deepseek_max_retries,
            retry_delay_seconds=self.settings.deepseek_retry_delay_seconds,
            provider="deepseek",
        )
        choices = data.get("choices") or []
        if not choices:
            raise GeminiAPIError("DeepSeek returned no choices.")
        message = choices[0].get("message") or {}
        text = message.get("content") or choices[0].get("text")
        if not isinstance(text, str) or not text.strip():
            raise GeminiAPIError("DeepSeek returned an empty reply.")
        return text.strip()

    async def _generate_text_gemini(self, prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"{self.settings.gemini_model}:generateContent"
        )

        data = await self._post_gemini_with_retry(
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

    def _provider_order(self) -> list[str]:
        primary = (self.settings.llm_provider or "deepseek").lower()
        fallback = (self.settings.llm_fallback_provider or "").lower()
        order: list[str] = []
        for provider in (primary, fallback):
            if provider in {"deepseek", "siliconflow"}:
                provider = "deepseek"
            if provider in {"gemini", "deepseek"} and provider not in order:
                order.append(provider)
        return order or ["deepseek", "gemini"]

    def _provider_enabled(self, provider: str) -> bool:
        provider = "deepseek" if provider == "siliconflow" else provider
        if provider == "deepseek":
            return bool(self.settings.deepseek_api_key)
        if provider == "gemini":
            return bool(self.settings.gemini_api_key)
        return False

    async def _post_openai_chat_with_retry(
        self,
        *,
        url: str,
        api_key: str,
        model: str,
        payload: dict[str, Any],
        timeout_seconds: float,
        max_retries: int,
        retry_delay_seconds: float,
        provider: str,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        timeout = httpx.Timeout(timeout_seconds)
        if self._is_circuit_open():
            raise GeminiAPIError(
                "AI 服务正在短暂恢复中，请稍后再试。",
                details={"circuit_open_until": self._circuit_open_until.isoformat() if self._circuit_open_until else None},
            )
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        url,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": api_key if api_key.lower().startswith("bearer ") else f"Bearer {api_key}",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    self._record_success()
                    return response.json()
            except (httpx.TimeoutException, httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                self._record_failure(max_failures=max_retries)
                if attempt >= max_retries:
                    break
                logger.bind(component="llm", provider=provider, model=model).warning(
                    "LLM request failed on attempt {attempt}/{max_retries}: {error}",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(exc),
                )
                await asyncio.sleep(retry_delay_seconds * attempt)

        raise GeminiAPIError(
            f"{provider} 服务暂时不可用，已重试 {max_retries} 次。",
            details={"last_error": str(last_error) if last_error else "unknown"},
        )

    async def _post_gemini_with_retry(self, *, url: str, payload: dict[str, Any]) -> dict[str, Any]:
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
                self._record_failure(max_failures=self.settings.gemini_max_retries)
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

    def _record_failure(self, *, max_failures: int | None = None) -> None:
        self.__class__._consecutive_failures += 1
        threshold = max_failures or self.settings.gemini_max_retries
        if self.__class__._consecutive_failures >= threshold:
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

    def _build_event_semantics_prompt(
        self,
        *,
        user_message: str,
        now: datetime,
        profile: Any | None,
        external_context: dict[str, Any] | None,
    ) -> str:
        profile_payload = {
            "home_location_name": getattr(profile, "home_location_name", None) if profile else None,
            "work_location_name": getattr(profile, "work_location_name", None) if profile else None,
        }
        context_payload = external_context or {}
        schema = {
            "goal_type": "event",
            "title": "string or null",
            "location_name": "string or null",
            "missing_fields": ["title"],
            "confidence": 0.0,
            "reasoning_summary": "short Chinese phrase",
        }
        return f"""
你是日程智能助手的语义理解模块。你的任务是从用户自然语言中抽取“要创建的日程”的语义槽位。

必须遵守：
- 以语义理解为准，不要按关键词或固定分隔符硬拆句子。
- title 是用户真正要做的事情/目的，不能是任意截取的片段。
- location_name 只填写物理地点/场所，不要把动作、人物、目的合并进地点。
- 如果地点不明确就填 null，不要猜。
- 不要执行任何创建/修改动作，只返回 JSON。
- 示例：“中午12点我要去驾校接李婷” 应理解为 title 可为“去驾校接李婷”或“接李婷”，location_name 为“驾校”，绝不能输出 title=“点我要” 或 location_name=“驾校接李婷”。

当前时间：{now.isoformat(timespec="minutes")}
用户画像：{json.dumps(profile_payload, ensure_ascii=False)}
外部上下文：{json.dumps(context_payload, ensure_ascii=False, default=str)}
用户消息：{user_message}

只返回一个 JSON 对象，字段形如：
{json.dumps(schema, ensure_ascii=False)}
""".strip()

    def _build_message_understanding_prompt(
        self,
        *,
        user_message: str,
        now: datetime,
        profile: Any | None,
        external_context: dict[str, Any] | None,
    ) -> str:
        profile_payload = {
            "home_location_name": getattr(profile, "home_location_name", None) if profile else None,
            "work_location_name": getattr(profile, "work_location_name", None) if profile else None,
        }
        context_payload = external_context or {}
        schema = {
            "intent": "create_event|create_task|reschedule_event|cancel_event|mark_event_completed|mark_task_completed|schedule_guidance|progress_followup|event_context_advice|unknown",
            "goal_type": "event|task|schedule_guidance|progress_followup|event_context_advice|unknown",
            "title": "event title or null",
            "location_name": "physical place or null",
            "task_content": "task content or null",
            "missing_fields": [],
            "ambiguities": [],
            "confidence": 0.0,
            "reasoning_summary": "short Chinese phrase",
        }
        return f"""
你是日程智能助手的 Understanding Specialist。你负责把用户自然语言理解成结构化目标，供后续规划和协商模块使用。

必须遵守：
- LLM 语义理解是主路径，不要用关键词、固定分隔符或正则式思路硬拆。
- 只做理解，不执行任何写操作。
- 写入日程/任务前必须交给 proposal/确认流程。
- title 是日程中真正要做的事情；location_name 只填写物理地点/场所。
- 对“去驾校接李婷”这类表达，地点是“驾校”，动作/目的可以是“去驾校接李婷”或“接李婷”。
- 如果无法可靠理解，intent 填 unknown，并把缺失项写入 missing_fields。

当前时间：{now.isoformat(timespec="minutes")}
用户画像：{json.dumps(profile_payload, ensure_ascii=False)}
外部上下文：{json.dumps(context_payload, ensure_ascii=False, default=str)}
用户消息：{user_message}

只返回一个 JSON 对象，字段形如：
{json.dumps(schema, ensure_ascii=False)}
""".strip()

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
