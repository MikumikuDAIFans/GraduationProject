"""Tests for the ChromaDB vector store wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.vector_store import VectorStore


@pytest.fixture
def mock_vector_store():
    """Create a VectorStore with fully mocked ChromaDB."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count.return_value = 0
    mock_client.get_or_create_collection.return_value = mock_collection

    with patch("app.core.vector_store.chromadb.PersistentClient", return_value=mock_client):
        with patch("app.core.vector_store.GeminiEmbeddingFunction", return_value=MagicMock()):
            store = VectorStore(persist_directory="./test_db")
            store._mock_client = mock_client
            store._mock_collection = mock_collection
            yield store


class TestVectorStoreInitialization:
    """Test vector store initialization."""

    def test_creates_three_collections(self):
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch("app.core.vector_store.chromadb.PersistentClient", return_value=mock_client):
            with patch("app.core.vector_store.GeminiEmbeddingFunction", return_value=MagicMock()):
                store = VectorStore(persist_directory="./test_db")
                assert set(store.collections.keys()) == {"habits", "experiences", "preferences"}
                assert mock_client.get_or_create_collection.call_count == 3

    def test_default_persist_directory(self):
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch("app.core.vector_store.chromadb.PersistentClient", return_value=mock_client):
            with patch("app.core.vector_store.GeminiEmbeddingFunction", return_value=MagicMock()):
                store = VectorStore()
                assert store.client is not None


class TestVectorStoreCRUD:
    """Test CRUD operations on the vector store."""

    def test_add_documents(self, mock_vector_store):
        store = mock_vector_store
        store.add("habits", ["morning routine"], [{"user": "u1"}], ["h1"])
        store._mock_collection.add.assert_called_once()

    def test_query_collection(self, mock_vector_store):
        store = mock_vector_store
        store.query("habits", ["exercise"], n_results=1)
        store._mock_collection.query.assert_called_once()

    def test_get_by_id(self, mock_vector_store):
        store = mock_vector_store
        store.get("habits", ids=["doc1"])
        store._mock_collection.get.assert_called_once()

    def test_delete_documents(self, mock_vector_store):
        store = mock_vector_store
        store.delete("habits", ids=["del1"])
        store._mock_collection.delete.assert_called_once()

    def test_count_collection(self, mock_vector_store):
        store = mock_vector_store
        store._mock_collection.count.return_value = 5
        assert store.count("habits") == 5

    def test_count_empty_collection(self, mock_vector_store):
        store = mock_vector_store
        store._mock_collection.count.return_value = 0
        assert store.count("habits") == 0


class TestVectorStoreCollections:
    """Test collection-specific operations."""

    def test_add_to_experiences(self, mock_vector_store):
        store = mock_vector_store
        store.add("experiences", ["meeting ran long"], [{"outcome": "rescheduled"}], ["exp1"])
        store._mock_collection.add.assert_called_once()

    def test_add_to_preferences(self, mock_vector_store):
        store = mock_vector_store
        store.add("preferences", ["prefers mornings"], [{"type": "time_pref"}], ["pref1"])
        store._mock_collection.add.assert_called_once()

    def test_query_with_where_filter(self, mock_vector_store):
        store = mock_vector_store
        store.query("habits", ["run"], where={"time": "morning"})
        call_kwargs = store._mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"time": "morning"}


class TestVectorStoreErrors:
    """Test error handling."""

    def test_add_unknown_collection_raises(self, mock_vector_store):
        store = mock_vector_store
        with pytest.raises(ValueError, match="Unknown collection"):
            store.add("nonexistent", ["doc"], [{}], ["id"])

    def test_query_unknown_collection_raises(self, mock_vector_store):
        store = mock_vector_store
        with pytest.raises(ValueError, match="Unknown collection"):
            store.query("nonexistent", ["query"])

    def test_get_unknown_collection_raises(self, mock_vector_store):
        store = mock_vector_store
        with pytest.raises(ValueError, match="Unknown collection"):
            store.get("nonexistent")

    def test_delete_unknown_collection_raises(self, mock_vector_store):
        store = mock_vector_store
        with pytest.raises(ValueError, match="Unknown collection"):
            store.delete("nonexistent", ids=["id"])

    def test_count_unknown_collection_raises(self, mock_vector_store):
        store = mock_vector_store
        with pytest.raises(ValueError, match="Unknown collection"):
            store.count("nonexistent")


class TestSafeAdd:
    """Test safe_add with fallback behavior."""

    def test_safe_add_success(self, mock_vector_store):
        store = mock_vector_store
        result = store.safe_add("habits", ["safe doc"], [{"user": "u1"}], ["safe1"])
        assert result is True

    def test_safe_add_failure_returns_false(self, mock_vector_store):
        store = mock_vector_store
        store._mock_collection.add.side_effect = Exception("Network error")
        result = store.safe_add("habits", ["fail doc"], [{"user": "u1"}], ["fail1"])
        assert result is False
