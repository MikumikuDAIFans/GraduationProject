"""Output adapters for various modalities."""

from .base import BaseOutputAdapter
from .gtts_adapter import GTTSOutputAdapter

__all__ = ["BaseOutputAdapter", "GTTSOutputAdapter"]
