"""Input adapters for various modalities."""

from .base import BaseInputAdapter
from .whisper_adapter import WhisperInputAdapter

__all__ = ["BaseInputAdapter", "WhisperInputAdapter"]
