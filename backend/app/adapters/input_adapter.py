"""Input adapter interface and text implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class InputAdapter(ABC):
    """Base class for input adapters."""

    @abstractmethod
    async def parse(self, payload: Any) -> dict[str, Any]:
        """Parse raw input into a normalized message payload."""


class TextInputAdapter(InputAdapter):
    """Default text input adapter."""

    async def parse(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, str):
            return {"message": payload, "metadata": {"source": "text"}}
        if isinstance(payload, dict):
            return {
                "message": payload.get("message", ""),
                "metadata": {"source": "text", **payload.get("metadata", {})},
            }
        return {"message": str(payload), "metadata": {"source": "text"}}


class VoiceInputAdapter(InputAdapter):
    """Placeholder for future voice input support."""

    async def parse(self, payload: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "Voice input adapter is not yet implemented. "
            "Set VOICE_INPUT_ENABLED=true and provide an STT service configuration."
        )
