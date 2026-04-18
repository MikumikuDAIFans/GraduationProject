"""ChromaDB vector store wrapper with Gemini Embedding."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from loguru import logger

from app.core.embedding import GeminiEmbeddingFunction

try:
    import chromadb
except ImportError:  # pragma: no cover - optional dependency fallback
    chromadb = SimpleNamespace(PersistentClient=None)


class VectorStore:
    """Wrapper around ChromaDB with Gemini Embedding API.

    Manages three collections:
    - user_habits: User habit patterns and routines
    - event_experiences: Historical event outcomes and lessons
    - user_preferences: User scheduling preferences and constraints
    """

    def __init__(self, persist_directory: str = "./chroma_db"):
        if chromadb.PersistentClient is None:
            raise RuntimeError(
                "ChromaDB is not installed. Install `chromadb` to enable vector store features."
            )
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.embed_fn = GeminiEmbeddingFunction()

        self.collections = {
            "habits": self._get_or_create("user_habits"),
            "experiences": self._get_or_create("event_experiences"),
            "preferences": self._get_or_create("user_preferences"),
        }

    def _get_or_create(self, name: str):
        """Get or create a ChromaDB collection."""
        return self.client.get_or_create_collection(
            name=name,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        collection: str,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """Add documents to a collection."""
        if collection not in self.collections:
            raise ValueError(f"Unknown collection: {collection}")
        self.collections[collection].add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info(f"Added {len(documents)} documents to {collection}")

    def query(
        self,
        collection: str,
        query_texts: list[str],
        n_results: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Query a collection with optional filters."""
        if collection not in self.collections:
            raise ValueError(f"Unknown collection: {collection}")
        kwargs: dict[str, Any] = {
            "query_texts": query_texts,
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        return self.collections[collection].query(**kwargs)

    def get(self, collection: str, ids: Optional[list[str]] = None) -> dict[str, Any]:
        """Get documents by ID from a collection."""
        if collection not in self.collections:
            raise ValueError(f"Unknown collection: {collection}")
        kwargs: dict[str, Any] = {}
        if ids:
            kwargs["ids"] = ids
        return self.collections[collection].get(**kwargs)

    def delete(self, collection: str, ids: list[str]) -> None:
        """Delete documents from a collection."""
        if collection not in self.collections:
            raise ValueError(f"Unknown collection: {collection}")
        self.collections[collection].delete(ids=ids)

    def count(self, collection: str) -> int:
        """Count documents in a collection."""
        if collection not in self.collections:
            raise ValueError(f"Unknown collection: {collection}")
        return self.collections[collection].count()

    def safe_add(
        self,
        collection: str,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> bool:
        """Safely add documents with fallback on network errors.

        Returns True if successful, False if fell back to SQLite.
        """
        try:
            self.add(collection, documents, metadatas, ids)
            return True
        except Exception as e:
            logger.warning(f"Vector store write failed, falling back: {e}")
            # In a full implementation, we would queue these for SQLite
            # For now, just log the failure
            return False
