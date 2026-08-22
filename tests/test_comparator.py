"""
Unit tests for the embedding comparator module.

Uses synthetic embeddings — no InsightFace model or webcam required.
"""

import numpy as np
import pytest

from app.config import settings
from app.database.driver_repository import DriverRecord
from app.face_recognition.comparator import (
    AuthResult,
    average_embeddings,
    cosine_similarity,
    find_best_match,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unit_vec(dim: int = settings.EMBEDDING_DIM, seed: int = 0) -> np.ndarray:
    """Return a deterministic random unit vector."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _make_driver(driver_id: int, name: str, seed: int) -> DriverRecord:
    """Create a DriverRecord with a deterministic embedding."""
    return DriverRecord(
        driver_id=driver_id,
        name=name,
        face_embedding=_unit_vec(seed=seed),
        created_at="2026-01-01T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# cosine_similarity tests
# ---------------------------------------------------------------------------

class TestCosineSimilarity:

    def test_identical_vectors(self):
        v = _unit_vec(seed=42)
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        a = np.zeros(settings.EMBEDDING_DIM, dtype=np.float32)
        b = np.zeros(settings.EMBEDDING_DIM, dtype=np.float32)
        a[0] = 1.0
        b[1] = 1.0
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors(self):
        v = _unit_vec(seed=7)
        assert cosine_similarity(v, -v) == pytest.approx(-1.0, abs=1e-6)

    def test_zero_vector_returns_zero(self):
        v = _unit_vec(seed=3)
        zero = np.zeros_like(v)
        assert cosine_similarity(v, zero) == 0.0

    def test_similarity_range(self):
        a = _unit_vec(seed=10)
        b = _unit_vec(seed=20)
        sim = cosine_similarity(a, b)
        assert -1.0 <= sim <= 1.0


# ---------------------------------------------------------------------------
# find_best_match tests
# ---------------------------------------------------------------------------

class TestFindBestMatch:

    def test_match_against_empty_db(self):
        probe = _unit_vec(seed=1)
        result = find_best_match(probe, [])
        assert result.is_match is False
        assert result.driver_name == "Unknown Driver"
        assert result.similarity == 0.0

    def test_exact_match(self):
        emb = _unit_vec(seed=5)
        driver = DriverRecord(
            driver_id=1,
            name="Alice",
            face_embedding=emb,
            created_at="2026-01-01T00:00:00+00:00",
        )
        result = find_best_match(emb, [driver], threshold=0.4)
        assert result.is_match is True
        assert result.driver_id == 1
        assert result.driver_name == "Alice"
        assert result.similarity == pytest.approx(1.0, abs=1e-5)

    def test_below_threshold(self):
        probe = _unit_vec(seed=100)
        driver = _make_driver(1, "Bob", seed=200)
        # Use a very high threshold to force rejection.
        result = find_best_match(probe, [driver], threshold=0.99)
        assert result.is_match is False
        assert result.driver_name == "Unknown Driver"

    def test_best_of_multiple_drivers(self):
        probe = _unit_vec(seed=10)
        # Create one driver with the same embedding as the probe.
        exact = DriverRecord(
            driver_id=2,
            name="Charlie",
            face_embedding=probe.copy(),
            created_at="2026-01-01T00:00:00+00:00",
        )
        others = [_make_driver(i, f"Driver{i}", seed=i * 100) for i in range(3, 6)]
        all_drivers = others + [exact]

        result = find_best_match(probe, all_drivers, threshold=0.4)
        assert result.is_match is True
        assert result.driver_name == "Charlie"


# ---------------------------------------------------------------------------
# average_embeddings tests
# ---------------------------------------------------------------------------

class TestAverageEmbeddings:

    def test_single_embedding(self):
        v = _unit_vec(seed=1)
        avg = average_embeddings([v])
        np.testing.assert_array_almost_equal(avg, v)

    def test_average_is_normalised(self):
        embs = [_unit_vec(seed=i) for i in range(5)]
        avg = average_embeddings(embs)
        assert np.linalg.norm(avg) == pytest.approx(1.0, abs=1e-5)

    def test_identical_embeddings_return_same(self):
        v = _unit_vec(seed=42)
        avg = average_embeddings([v, v, v])
        np.testing.assert_array_almost_equal(avg, v)

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="empty"):
            average_embeddings([])
