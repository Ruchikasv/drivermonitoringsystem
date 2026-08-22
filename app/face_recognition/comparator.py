"""
Embedding comparison and matching logic.

Pure-NumPy functions — no InsightFace dependency — so these can be
tested easily with synthetic embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.config import settings
from app.database.driver_repository import DriverRecord


@dataclass
class AuthResult:
    """
    Result of comparing a probe embedding against the driver database.

    Attributes
    ----------
    is_match : bool
        ``True`` if similarity ≥ threshold.
    driver_id : int or None
        ID of the matched driver, or ``None`` if no match.
    driver_name : str
        Name of the matched driver, or ``"Unknown Driver"``.
    similarity : float
        Cosine similarity to the best candidate (0.0–1.0).
    """

    is_match: bool
    driver_id: Optional[int]
    driver_name: str
    similarity: float


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.

    If both vectors are L2-normalised (as ArcFace embeddings are),
    this reduces to a dot product.

    Parameters
    ----------
    a, b : np.ndarray
        1-D vectors of the same length.

    Returns
    -------
    float
        Similarity in the range [-1, 1].
    """
    dot = float(np.dot(a, b))
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def find_best_match(
    probe_embedding: np.ndarray,
    registered_drivers: list[DriverRecord],
    threshold: float | None = None,
) -> AuthResult:
    """
    Compare a probe embedding against all registered drivers.

    Parameters
    ----------
    probe_embedding : np.ndarray
        The 512-d embedding from the face in the current frame.
    registered_drivers : list[DriverRecord]
        All drivers loaded from the database.
    threshold : float, optional
        Minimum similarity for a positive match.
        Defaults to ``settings.RECOGNITION_THRESHOLD``.

    Returns
    -------
    AuthResult
        Contains the best match (or "Unknown Driver" if below threshold).
    """
    if threshold is None:
        threshold = settings.RECOGNITION_THRESHOLD

    if not registered_drivers:
        return AuthResult(
            is_match=False,
            driver_id=None,
            driver_name="Unknown Driver",
            similarity=0.0,
        )

    best_similarity = -1.0
    best_driver: Optional[DriverRecord] = None

    for driver in registered_drivers:
        sim = cosine_similarity(probe_embedding, driver.face_embedding)
        if sim > best_similarity:
            best_similarity = sim
            best_driver = driver

    if best_driver is not None and best_similarity >= threshold:
        return AuthResult(
            is_match=True,
            driver_id=best_driver.driver_id,
            driver_name=best_driver.name,
            similarity=best_similarity,
        )

    return AuthResult(
        is_match=False,
        driver_id=None,
        driver_name="Unknown Driver",
        similarity=best_similarity,
    )


def average_embeddings(embeddings: list[np.ndarray]) -> np.ndarray:
    """
    Compute the mean of multiple embeddings and re-normalise to unit length.

    Used during registration to combine several capture frames into a
    single robust reference embedding.

    Parameters
    ----------
    embeddings : list[np.ndarray]
        List of L2-normalised 512-d vectors.

    Returns
    -------
    np.ndarray
        The averaged and re-normalised embedding.

    Raises
    ------
    ValueError
        If the list is empty.
    """
    if not embeddings:
        raise ValueError("Cannot average an empty list of embeddings.")

    mean = np.mean(embeddings, axis=0).astype(np.float32)
    norm = np.linalg.norm(mean)

    if norm == 0:
        raise ValueError(
            "Averaged embedding has zero norm — this should not happen "
            "with valid face embeddings."
        )

    return mean / norm
