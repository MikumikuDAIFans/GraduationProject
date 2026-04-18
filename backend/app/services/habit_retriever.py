"""Habit retriever service — semantic search and recommendation."""

from __future__ import annotations

from typing import Any, Optional

from app.core.vector_store import VectorStore


class HabitRetriever:
    """Retrieves habits and preferences from vector store for assistant use."""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    async def suggest_time(
        self,
        activity: str,
        context: str = "",
        user_id: Optional[str] = None,
        n_results: int = 3,
    ) -> Optional[dict[str, Any]]:
        """Suggest a time based on user's habits for a given activity.

        Example: user says "做饭" → retrieves "晚上6点做饭" habit.
        """
        query = f"{activity} {context}".strip()
        filters = {"type": "routine"}
        if user_id:
            filters["user_id"] = user_id

        try:
            results = self.vector_store.query(
                collection="habits",
                query_texts=[query],
                n_results=n_results,
                where=filters,
            )
        except Exception as e:
            # Fallback if vector store is unavailable
            return None

        if not results or not results.get("metadatas") or not results["metadatas"][0]:
            return None

        # Return the highest confidence match above threshold
        for i, metadata in enumerate(results["metadatas"][0]):
            if metadata.get("confidence", 0) > 0.7:
                return {
                    "time_pattern": metadata.get("time_pattern"),
                    "confidence": metadata.get("confidence"),
                    "habit_id": results.get("ids", [[]])[0][i] if results.get("ids") else None,
                    "activity": metadata.get("activity"),
                }

        return None

    async def check_preference(
        self,
        proposal: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Check if a proposal violates user preferences.

        Returns list of conflicting preferences.
        """
        query_parts = []
        if proposal.get("time"):
            query_parts.append(str(proposal["time"]))
        if proposal.get("type"):
            query_parts.append(proposal["type"])
        if proposal.get("title"):
            query_parts.append(proposal["title"])

        query = " ".join(query_parts)
        filters = {"polarity": "negative"}
        if user_id:
            filters["user_id"] = user_id

        try:
            results = self.vector_store.query(
                collection="preferences",
                query_texts=[query],
                n_results=5,
                where=filters,
            )
        except Exception:
            return []

        warnings = []
        if results and results.get("metadatas") and results["metadatas"][0]:
            for i, metadata in enumerate(results["metadatas"][0]):
                if metadata.get("strength", 0) > 0.7:
                    warnings.append({
                        "preference": metadata.get("description", ""),
                        "strength": metadata.get("strength"),
                        "category": metadata.get("category", ""),
                    })

        return warnings

    async def get_similar_experience(
        self,
        situation: str,
        user_id: Optional[str] = None,
        n_results: int = 3,
    ) -> list[dict[str, Any]]:
        """Retrieve similar past experiences for a given situation."""
        filters = {}
        if user_id:
            filters["user_id"] = user_id

        try:
            results = self.vector_store.query(
                collection="experiences",
                query_texts=[situation],
                n_results=n_results,
                where=filters if filters else None,
            )
        except Exception:
            return []

        experiences = []
        if results and results.get("metadatas") and results["metadatas"][0]:
            for i, metadata in enumerate(results["metadatas"][0]):
                experiences.append({
                    "description": results.get("documents", [[]])[0][i] if results.get("documents") else "",
                    "metadata": metadata,
                    "distance": results.get("distances", [[]])[0][i] if results.get("distances") else None,
                })

        return experiences

    async def get_relevant_habits(
        self,
        activity: str,
        user_id: Optional[str] = None,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Get all relevant habits for a given activity."""
        filters = {}
        if user_id:
            filters["user_id"] = user_id

        try:
            results = self.vector_store.query(
                collection="habits",
                query_texts=[activity],
                n_results=n_results,
                where=filters if filters else None,
            )
        except Exception:
            return []

        habits = []
        if results and results.get("metadatas") and results["metadatas"][0]:
            for i, metadata in enumerate(results["metadatas"][0]):
                habits.append({
                    "id": results.get("ids", [[]])[0][i] if results.get("ids") else None,
                    "metadata": metadata,
                    "distance": results.get("distances", [[]])[0][i] if results.get("distances") else None,
                })

        return habits
