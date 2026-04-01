"""gTTS-based speech synthesis adapter."""

from __future__ import annotations

import asyncio
from io import BytesIO

from app.core.config import get_settings
from app.output_adapters.base import BaseOutputAdapter


class GTTSOutputAdapter(BaseOutputAdapter):
    """Use gTTS to synthesize speech audio."""

    def __init__(self, lang: str | None = None) -> None:
        self.settings = get_settings()
        self.lang = lang or "zh-CN"

    async def synthesize(self, text: str) -> bytes:
        try:
            from gtts import gTTS  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("gTTS dependency is not installed.") from exc

        buffer = BytesIO()

        def _write_audio():
            speech = gTTS(text=text, lang=self.lang)
            speech.write_to_fp(buffer)
            return buffer.getvalue()

        return await asyncio.to_thread(_write_audio)
