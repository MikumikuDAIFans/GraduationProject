"""Gemini Embedding API adapter for ChromaDB."""

from __future__ import annotations

import os

from chromadb import Documents, EmbeddingFunction, Embeddings
from google import genai
from google.genai import types
from loguru import logger


class GeminiEmbeddingFunction(EmbeddingFunction):
    """Gemini Embedding API adapter for ChromaDB.

    Uses Google's text-embedding-004 model to generate embeddings
    via the Gemini API, eliminating the need for local model files.
    """

    def __init__(self, model_name: str = "text-embedding-004"):
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
