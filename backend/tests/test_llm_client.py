from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import httpx

from app.services.debug_observability import debug_observability, redact_debug_value
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


def test_debug_redaction_removes_sensitive_values() -> None:
    redacted = redact_debug_value(
        {
            "Authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456",
            "api_key": "sk-abcdefghijklmnopqrstuvwxyz",
            "nested": {"token": "secret-token-value", "safe": "visible"},
        }
    )

    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "visible"


def test_debug_redaction_keeps_usage_token_counts() -> None:
    redacted = redact_debug_value(
        {
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 5,
                "total_tokens": 17,
            },
            "access_token": "abcdefghijklmnopqrstuvwxyz1234567890",
        }
    )

    assert redacted["usage"]["prompt_tokens"] == 12
    assert redacted["usage"]["completion_tokens"] == 5
    assert redacted["usage"]["total_tokens"] == 17
    assert redacted["access_token"] == "[REDACTED]"


def test_llm_trace_records_fallback_success_without_secret() -> None:
    async def scenario() -> None:
        debug_observability.clear()
        client = GeminiClient()
        client.settings.deepseek_api_key = "deepseek-secret-key"
        client.settings.gemini_api_key = "gemini-secret-key"
        client.trace_context = {"purpose": "unit-test", "session_id": 7}

        async def fail_deepseek(_prompt: str) -> str:
            raise RuntimeError("primary down")

        async def post_gemini(**_kwargs):
            debug_observability.record_llm_trace(
                provider="gemini",
                model=client.settings.gemini_model,
                purpose=client.trace_context.get("purpose") or "unit-test",
                status="fallback_success" if client.trace_context.get("_fallback_attempt") else "success",
                request_payload={"api_key": "sk-should-not-leak", "prompt": "hello"},
                raw_response={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
                parsed_result={"text": "ok"},
                session_id=client.trace_context.get("session_id"),
            )
            return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

        client._generate_text_deepseek = fail_deepseek  # type: ignore[method-assign]
        client._post_gemini_with_retry = post_gemini  # type: ignore[method-assign]

        assert await client.generate_text("hello") == "ok"
        traces = debug_observability.list_llm_traces()
        assert traces[0]["status"] == "fallback_success"
        assert traces[0]["request_payload_redacted"]["api_key"] == "[REDACTED]"
        assert traces[0]["session_id"] == 7

    asyncio.run(scenario())


def test_llm_trace_records_parse_error() -> None:
    debug_observability.clear()
    client = GeminiClient()
    client.trace_context = {"purpose": "parse-test", "request_id": "req-1"}

    try:
        client._parse_json_payload("not json")
    except Exception:
        pass
    else:
        raise AssertionError("invalid JSON should fail")

    traces = debug_observability.list_llm_traces()
    assert traces[0]["status"] == "parse_error"
    assert traces[0]["request_id"] == "req-1"
    assert traces[0]["raw_response_redacted"] == "not json"


def test_openai_post_trace_records_http_error(monkeypatch) -> None:
    async def scenario() -> None:
        debug_observability.clear()
        client = GeminiClient()
        client.trace_context = {"purpose": "http-test"}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *args, **kwargs):
                request = httpx.Request("POST", "https://example.test")
                response = httpx.Response(500, request=request)
                return SimpleNamespace(
                    raise_for_status=lambda: (_ for _ in ()).throw(httpx.HTTPStatusError("boom", request=request, response=response))
                )

        monkeypatch.setattr("app.tools.gemini.httpx.AsyncClient", FakeAsyncClient)

        try:
            await client._post_openai_chat_with_retry(
                url="https://example.test",
                api_key="sk-secret",
                model="model",
                payload={"messages": [{"role": "user", "content": "hello"}]},
                timeout_seconds=1,
                max_retries=1,
                retry_delay_seconds=0,
                provider="deepseek",
            )
        except Exception:
            pass
        else:
            raise AssertionError("HTTP error should fail")

        traces = debug_observability.list_llm_traces()
        assert traces[0]["status"] == "error"
        assert traces[0]["provider"] == "deepseek"
        assert traces[0]["request_payload_redacted"]["messages"][0]["content"] == "hello"

    asyncio.run(scenario())
