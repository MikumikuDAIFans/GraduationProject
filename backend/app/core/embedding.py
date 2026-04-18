"""Gemini Embedding API adapter for ChromaDB."""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

try:
    from google import genai
except ImportError:  # pragma: no cover - optional dependency fallback
    genai = None

try:
    from chromadb import Documents, EmbeddingFunction, Embeddings
except ImportError:  # pragma: no cover - optional dependency fallback
    Documents = list[str]
    Embeddings = list[list[float]]

    class EmbeddingFunction:  # type: ignore[override]
        """Fallback base class when ChromaDB is unavailable."""

        pass


class GeminiEmbeddingFunction(EmbeddingFunction):
    """Gemini Embedding API adapter for ChromaDB.

    Uses Google's text-embedding-004 model to generate embeddings
    via the Gemini API, eliminating the need for local model files.
    """

    def __init__(self, model_name: str = "text-embedding-004"):
        if genai is None:
            raise RuntimeError(
                "Google GenAI SDK is not installed. Install `google-genai` to enable Gemini embeddings."
            )
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def __call__(self, input: Documents) -> Embeddings:
        """Generate embeddings for a list of texts via Gemini API."""
        embeddings = []
        for text in input:
            try:
                result = self.client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                )
                embeddings.append(result.embeddings[0].values)
            except Exception as e:
                logger.warning(f"Gemini embedding failed for text '{text[:50]}...': {e}")
                # Return zero vector as fallback (dimension 768 for text-embedding-004)
                embeddings.append([0.0] * 768)
        return embeddings
