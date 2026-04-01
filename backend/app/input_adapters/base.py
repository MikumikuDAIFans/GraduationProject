"""Base class for input adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseInputAdapter(ABC):
    """输入适配器基类."""

    @abstractmethod
    async def process_input(self, input_data: bytes | str) -> str:
        """处理输入并返回文本。"""
