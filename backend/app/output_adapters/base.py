"""Base class for output adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseOutputAdapter(ABC):
    """输出适配器基类."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """将文本合成为可播放音频字节。"""
