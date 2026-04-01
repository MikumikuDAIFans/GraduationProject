"""Whisper speech-to-text adapter."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.input_adapters.base import BaseInputAdapter


class WhisperInputAdapter(BaseInputAdapter):
    """OpenAI Whisper 语音识别适配器."""

    def __init__(self, model_size: str | None = None) -> None:
        self.settings = get_settings()
        self.model_size = model_size or self.settings.voice_input_model
        self._model: Any | None = None

    def _load_model(self):
        if self._model is None:
            try:
                import whisper  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError("Whisper dependency is not installed.") from exc
            self._model = whisper.load_model(self.model_size)
        return self._model

    async def process_input(self, input_data: bytes | str) -> str:
        if isinstance(input_data, str):
            return input_data

        model = self._load_model()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(input_data)
            temp_path = Path(temp_file.name)

        try:
            result = await asyncio.to_thread(model.transcribe, str(temp_path), language="zh")
            return str(result["text"]).strip()
        finally:
            temp_path.unlink(missing_ok=True)
