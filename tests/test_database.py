"""
Unit tests for the database layer.

All tests use an in-memory SQLite database — no webcam or model required.
"""

import numpy as np
import pytest

from app.config import settings
from app.database.connection import get_connection, init_db
from app.database.driver_repository import (
    DriverRepository,
    _deserialize_embedding,
    _serialize_embedding,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn():
    """Yield an initialised in-memory database connection."""
    conn = get_connection(db_path=":memory:")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def repo(db_conn):
    """Yield a DriverRepository backed by the in-memory database."""
    return DriverRepository(db_conn)


def _random_embedding(dim: int = settings.EMBEDDING_DIM) -> np.ndarray:
    """Generate a random L2-normalised embedding for testing."""
    vec = np.random.randn(dim).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec


# ---------------------------------------------------------------------------
# Serialisation tests
# ---------------------------------------------------------------------------

class TestEmbeddingSerialization:
    """Tests for the low-level serialize/deserialize helpers."""

    def test_roundtrip_preserves_values(self):
        original = _random_embedding()
        restored = _deserialize_embedding(_serialize_embedding(original))
        np.testing.assert_array_almost_equal(original, restored)

    def test_serialized_size(self):
        emb = _random_embedding()
        blob = _serialize_embedding(emb)
        assert len(blob) == settings.EMBEDDING_DIM * 4  # float32 = 4 bytes

    def test_dtype_is_float32(self):
        emb = np.random.randn(settings.EMBEDDING_DIM).astype(np.float64)
        restored = _deserialize_embedding(_serialize_embedding(emb))
        assert restored.dtype == np.float32


# ---------------------------------------------------------------------------
# Repository CRUD tests
# ---------------------------------------------------------------------------

class TestDriverRepository:
    """Tests for DriverRepository CRUD operations."""

    def test_add_driver_returns_id(self, repo):
        emb = _random_embedding()
        driver_id = repo.add_driver("Alice", emb)
        assert isinstance(driver_id, int)
        assert driver_id >= 1

    def test_add_and_retrieve_driver(self, repo):
        emb = _random_embedding()
        driver_id = repo.add_driver("Bob", emb)

        driver = repo.get_driver_by_id(driver_id)
        assert driver is not None
        assert driver.name == "Bob"
        assert driver.driver_id == driver_id
        np.testing.assert_array_almost_equal(driver.face_embedding, emb)

    def test_get_nonexistent_driver_returns_none(self, repo):
        assert repo.get_driver_by_id(9999) is None

    def test_get_all_drivers_empty(self, repo):
        drivers = repo.get_all_drivers()
        assert drivers == []

    def test_get_all_drivers_multiple(self, repo):
        repo.add_driver("Alice", _random_embedding())
        repo.add_driver("Bob", _random_embedding())
        repo.add_driver("Charlie", _random_embedding())

        drivers = repo.get_all_drivers()
        assert len(drivers) == 3
        names = {d.name for d in drivers}
        assert names == {"Alice", "Bob", "Charlie"}

    def test_get_driver_count(self, repo):
        assert repo.get_driver_count() == 0
        repo.add_driver("Alice", _random_embedding())
        assert repo.get_driver_count() == 1
        repo.add_driver("Bob", _random_embedding())
        assert repo.get_driver_count() == 2

    def test_delete_existing_driver(self, repo):
        driver_id = repo.add_driver("Alice", _random_embedding())
        assert repo.delete_driver(driver_id) is True
        assert repo.get_driver_by_id(driver_id) is None

    def test_delete_nonexistent_driver_returns_false(self, repo):
        assert repo.delete_driver(9999) is False

    def test_add_driver_rejects_wrong_shape(self, repo):
        bad_emb = np.random.randn(256).astype(np.float32)
        with pytest.raises(ValueError, match="Expected embedding shape"):
            repo.add_driver("BadShape", bad_emb)

    def test_created_at_is_populated(self, repo):
        driver_id = repo.add_driver("Alice", _random_embedding())
        driver = repo.get_driver_by_id(driver_id)
        assert driver is not None
        assert len(driver.created_at) > 0  # ISO-8601 string
