"""Output adapter interface and text implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OutputAdapter(ABC):
    """Base class for output adapters."""

    @abstractmethod
    async def render(self, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render assistant output into the target format."""


class TextOutputAdapter(OutputAdapter):
    """Default text output adapter."""

    async def render(self, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "content": message,
            "content_type": "text/plain",
            "metadata": {"source": "text", **(metadata or {})},
        }


class VoiceOutputAdapter(OutputAdapter):
    """Placeholder for future voice output support."""

    async def render(self, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError(
            "Voice output adapter is not yet implemented. "
            "Set VOICE_OUTPUT_ENABLED=true and provide a TTS service configuration."
        )
