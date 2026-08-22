"""
Webcam capture module.

Provides a context-manager class for safe webcam access with
automatic resource cleanup.
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class CameraError(Exception):
    """Raised when the camera cannot be opened or becomes unavailable."""


class WebcamCapture:
    """
    Manages a single webcam device via OpenCV VideoCapture.

    Usage::

        with WebcamCapture() as cam:
            frame = cam.read_frame()

    Parameters
    ----------
    camera_index : int, optional
        Device index.  Defaults to ``settings.CAMERA_INDEX``.
    """

    def __init__(self, camera_index: int | None = None) -> None:
        self._camera_index = (
            camera_index if camera_index is not None else settings.CAMERA_INDEX
        )
        self._cap: Optional[cv2.VideoCapture] = None

    # -- Context manager ------------------------------------------------------

    def __enter__(self) -> "WebcamCapture":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    # -- Public API -----------------------------------------------------------

    def open(self) -> None:
        """
        Open the webcam.

        Raises
        ------
        CameraError
            If the device cannot be opened.
        """
        logger.info("Opening camera index %d …", self._camera_index)
        self._cap = cv2.VideoCapture(self._camera_index)

        if not self._cap.isOpened():
            self._cap.release()
            self._cap = None
            raise CameraError(
                f"Cannot open camera at index {self._camera_index}. "
                "Check that the device is connected and not in use by another app."
            )

        logger.info("Camera opened successfully.")

    def read_frame(self) -> np.ndarray:
        """
        Grab a single BGR frame from the webcam.

        Returns
        -------
        np.ndarray
            The captured frame (H×W×3, dtype uint8, BGR colour order).

        Raises
        ------
        CameraError
            If the camera is not open or the read fails (e.g. device disconnected).
        """
        if self._cap is None or not self._cap.isOpened():
            raise CameraError("Camera is not open. Call open() first.")

        ret, frame = self._cap.read()

        if not ret or frame is None:
            raise CameraError(
                "Failed to read frame from camera. "
                "The device may have been disconnected."
            )

        return frame

    def release(self) -> None:
        """Release the webcam device (idempotent)."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Camera released.")

    @property
    def is_open(self) -> bool:
        """Check whether the camera device is currently open."""
        return self._cap is not None and self._cap.isOpened()
