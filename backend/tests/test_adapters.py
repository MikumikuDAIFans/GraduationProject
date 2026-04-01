from __future__ import annotations

import asyncio

import pytest

from app.adapters.input_adapter import TextInputAdapter, VoiceInputAdapter
from app.adapters.output_adapter import TextOutputAdapter, VoiceOutputAdapter


def test_text_input_adapter_parses_string() -> None:
    adapter = TextInputAdapter()
    result = asyncio.run(adapter.parse("Hello world"))
    assert result["message"] == "Hello world"
    assert result["metadata"]["source"] == "text"


def test_text_input_adapter_parses_dict() -> None:
    adapter = TextInputAdapter()
    result = asyncio.run(adapter.parse({"message": "hi", "metadata": {"lang": "zh"}}))
    assert result["message"] == "hi"
    assert result["metadata"]["lang"] == "zh"


def test_text_output_adapter_renders() -> None:
    adapter = TextOutputAdapter()
    result = asyncio.run(adapter.render("Your meeting is at 3pm."))
    assert result["content"] == "Your meeting is at 3pm."
    assert result["content_type"] == "text/plain"


def test_voice_input_adapter_not_implemented() -> None:
    adapter = VoiceInputAdapter()
    with pytest.raises(NotImplementedError):
        asyncio.run(adapter.parse(b"audio-bytes"))


def test_voice_output_adapter_not_implemented() -> None:
    adapter = VoiceOutputAdapter()
    with pytest.raises(NotImplementedError):
        asyncio.run(adapter.render("hello"))
