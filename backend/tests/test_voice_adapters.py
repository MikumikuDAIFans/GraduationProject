from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from app.input_adapters import WhisperInputAdapter
from app.output_adapters import GTTSOutputAdapter


def test_whisper_input_adapter_passthrough_text() -> None:
    adapter = WhisperInputAdapter(model_size="tiny")
    result = asyncio.run(adapter.process_input("hello"))
    assert result == "hello"


def test_whisper_input_adapter_transcribes_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = WhisperInputAdapter(model_size="tiny")

    class FakeModel:
        def transcribe(self, path: str, language: str = "zh"):
            return {"text": " 测试语音 "}

    monkeypatch.setattr(adapter, "_load_model", lambda: FakeModel())
    result = asyncio.run(adapter.process_input(b"fake-audio"))
    assert result == "测试语音"


def test_gtts_output_adapter_synthesizes_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeGTTS:
        def __init__(self, text: str, lang: str):
            self.text = text
            self.lang = lang

        def write_to_fp(self, fp):
            fp.write(b"mp3-data")

    monkeypatch.setitem(sys.modules, "gtts", SimpleNamespace(gTTS=FakeGTTS))
    adapter = GTTSOutputAdapter(lang="zh-CN")
    audio = asyncio.run(adapter.synthesize("你好"))
    assert audio == b"mp3-data"
