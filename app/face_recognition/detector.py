"""
Face detection and embedding extraction using InsightFace.

Wraps the InsightFace ``FaceAnalysis`` pipeline so the rest of the
application doesn't depend on InsightFace internals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DetectedFace:
    """
    Result of detecting one face in a frame.

    Attributes
    ----------
    bbox : np.ndarray
        Bounding box ``[x1, y1, x2, y2]``.
    score : float
        Detection confidence (0–1).
    embedding : np.ndarray
        512-dimensional L2-normalised ArcFace embedding.
    """

    bbox: np.ndarray
    score: float
    embedding: np.ndarray


class FaceDetector:
    """
    Detects faces and extracts ArcFace embeddings.

    The heavy InsightFace model is loaded **lazily** on the first call
    to :meth:`detect_faces`, not at import time.

    Parameters
    ----------
    model_name : str, optional
        InsightFace model pack (default from settings).
    model_dir : str, optional
        Directory where model weights are cached.
    """

    def __init__(
        self,
        model_name: str | None = None,
        model_dir: str | None = None,
    ) -> None:
        self._model_name = model_name or settings.INSIGHTFACE_MODEL_NAME
        self._model_dir = model_dir or str(settings.MODEL_DIR)
        self._app = None  # Lazy-loaded InsightFace FaceAnalysis

    # -- Lazy model loading ---------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        """Load the InsightFace model if not already loaded."""
        if self._app is not None:
            return

        logger.info(
            "Loading InsightFace model '%s' from '%s' …",
            self._model_name,
            self._model_dir,
        )

        try:
            import insightface
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise ImportError(
                "InsightFace is not installed.  Run:\n"
                "  pip install insightface onnxruntime"
            ) from exc

        self._app = FaceAnalysis(
            name=self._model_name,
            root=self._model_dir,
            allowed_modules=["detection", "recognition"],
        )
        # ctx_id=0 → use first GPU if available; -1 → CPU only.
        # For a laptop prototype, CPU is fine.
        self._app.prepare(ctx_id=-1, det_size=(640, 640))
        logger.info("InsightFace model loaded successfully.")

    # -- Public API -----------------------------------------------------------

    def detect_faces(
        self,
        frame: np.ndarray,
        min_confidence: float | None = None,
    ) -> list[DetectedFace]:
        """
        Detect all faces in a BGR frame and extract embeddings.

        Parameters
        ----------
        frame : np.ndarray
            A BGR image (H×W×3, uint8) from OpenCV.
        min_confidence : float, optional
            Minimum detection score.  Defaults to
            ``settings.DETECTION_CONFIDENCE``.

        Returns
        -------
        list[DetectedFace]
            Detected faces sorted by confidence (highest first).
        """
        self._ensure_model_loaded()

        if min_confidence is None:
            min_confidence = settings.DETECTION_CONFIDENCE

        raw_faces = self._app.get(frame)  # type: ignore[union-attr]

        results: list[DetectedFace] = []
        for face in raw_faces:
            score = float(face.det_score)
            if score < min_confidence:
                continue

            results.append(
                DetectedFace(
                    bbox=face.bbox.astype(np.int32),
                    score=score,
                    embedding=face.normed_embedding,  # Already L2-normalised.
                )
            )

        # Sort by confidence — highest first.
        results.sort(key=lambda f: f.score, reverse=True)
        return results

    def detect_single_face(
        self,
        frame: np.ndarray,
        min_confidence: float | None = None,
    ) -> Optional[DetectedFace]:
        """
        Detect exactly one face.

        Returns
        -------
        DetectedFace or None
            The detected face, or ``None`` if zero or multiple faces are found.

        Notes
        -----
        Callers can check whether ``None`` was returned because of zero
        or multiple faces by calling :meth:`detect_faces` directly.
        """
        faces = self.detect_faces(frame, min_confidence=min_confidence)

        if len(faces) != 1:
            if len(faces) == 0:
                logger.debug("No face detected in frame.")
            else:
                logger.debug(
                    "Multiple faces detected (%d) — expected exactly 1.",
                    len(faces),
                )
            return None

        return faces[0]
