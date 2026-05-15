from __future__ import annotations

import asyncio

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
