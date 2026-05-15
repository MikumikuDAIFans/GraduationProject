from __future__ import annotations

import asyncio
from datetime import datetime

from app.tools.gemini import GeminiClient


def test_llm_client_uses_deepseek_first_then_gemini_fallback() -> None:
    async def scenario() -> None:
        client = GeminiClient()
        client.settings.llm_provider = "deepseek"
        client.settings.llm_fallback_provider = "gemini"
        client.settings.deepseek_api_key = "deepseek-test-key"
        client.settings.gemini_api_key = "gemini-test-key"
        calls: list[str] = []

        async def fail_deepseek(prompt: str) -> str:
            calls.append(f"deepseek:{prompt}")
            raise RuntimeError("deepseek unavailable")

        async def ok_gemini(prompt: str) -> str:
            calls.append(f"gemini:{prompt}")
            return "gemini fallback reply"

        client._generate_text_deepseek = fail_deepseek  # type: ignore[method-assign]
        client._generate_text_gemini = ok_gemini  # type: ignore[method-assign]

        result = await client.generate_text("hello")

        assert result == "gemini fallback reply"
        assert calls == ["deepseek:hello", "gemini:hello"]

    asyncio.run(scenario())


def test_llm_client_enabled_when_deepseek_key_is_configured() -> None:
    client = GeminiClient()
    client.settings.llm_provider = "deepseek"
    client.settings.llm_fallback_provider = "gemini"
    client.settings.deepseek_api_key = "deepseek-test-key"
    client.settings.gemini_api_key = None

    assert client.enabled is True


def test_extract_message_understanding_rejects_invalid_schema() -> None:
    async def scenario() -> None:
        client = GeminiClient()
        client.settings.llm_provider = "deepseek"
        client.settings.deepseek_api_key = "deepseek-test-key"

        async def invalid_payload(_prompt: str) -> str:
            return '{"intent":"invent_calendar","goal_type":"event","confidence":0.9}'

        client._generate_text = invalid_payload  # type: ignore[method-assign]

        try:
            await client.extract_message_understanding(
                user_message="明天下午3点去学校",
                now=datetime(2026, 5, 15, 9, 0),
            )
        except Exception as exc:
            assert "invalid message understanding" in str(exc)
        else:
            raise AssertionError("invalid LLM schema should be rejected")

    asyncio.run(scenario())
