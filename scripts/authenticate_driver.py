#!/usr/bin/env python
"""
Authenticate a driver via the laptop webcam.

Usage::

    python -m scripts.authenticate_driver

The script will:
1. Open the webcam and show a live preview.
2. Continuously detect faces and compare against registered drivers.
3. Display the authentication result on screen.
4. Press Q to quit.
"""

from __future__ import annotations

import logging
import sys

import cv2
import numpy as np

# Add project root to path so we can import app.* when run as a script.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from app.camera.capture import CameraError, WebcamCapture
from app.config import settings
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.face_recognition.comparator import find_best_match
from app.face_recognition.detector import FaceDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# Colours (BGR)
GREEN = (0, 255, 0)
RED = (0, 0, 255)
YELLOW = (0, 255, 255)
WHITE = (255, 255, 255)


def _draw_text(
    frame: np.ndarray,
    text: str,
    position: tuple[int, int],
    colour: tuple[int, int, int] = WHITE,
    scale: float = 0.7,
    thickness: int = 2,
) -> None:
    """Draw text on a frame."""
    cv2.putText(
        frame, text, position,
        cv2.FONT_HERSHEY_SIMPLEX, scale, colour, thickness,
    )


def _draw_face_box(
    frame: np.ndarray,
    bbox: np.ndarray,
    colour: tuple[int, int, int],
    label: str = "",
) -> None:
    """Draw a bounding box and optional label around a face."""
    x1, y1, x2, y2 = bbox
    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), colour, 2)
    if label:
        cv2.putText(
            frame, label, (int(x1), int(y1) - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2,
        )


def main() -> None:
    # --- 1. Set up database --------------------------------------------------
    conn = get_connection()
    init_db(conn)
    repo = DriverRepository(conn)

    registered_drivers = repo.get_all_drivers()
    driver_count = len(registered_drivers)

    print("\n" + "=" * 50)
    print("  DRIVER AUTHENTICATION")
    print("=" * 50)
    print(f"  Registered drivers: {driver_count}")
    print(f"  Threshold         : {settings.RECOGNITION_THRESHOLD}")
    print("=" * 50)

    if driver_count == 0:
        print("\n⚠  No drivers registered. Run register_driver.py first.")
        conn.close()
        sys.exit(1)

    # --- 2. Set up face detector ---------------------------------------------
    detector = FaceDetector()

    # --- 3. Open webcam and run continuous authentication ---------------------
    print(f"\nOpening webcam (index {settings.CAMERA_INDEX}) …")
    print("Press Q to quit.\n")

    try:
        with WebcamCapture() as cam:
            while True:
                frame = cam.read_frame()
                display = frame.copy()

                faces = detector.detect_faces(frame)

                if len(faces) == 0:
                    _draw_text(display, "No face detected", (10, 30), RED)

                elif len(faces) > 1:
                    _draw_text(
                        display,
                        f"Multiple faces detected ({len(faces)})",
                        (10, 30),
                        RED,
                    )
                    for f in faces:
                        _draw_face_box(display, f.bbox, RED)

                else:
                    face = faces[0]
                    result = find_best_match(
                        face.embedding,
                        registered_drivers,
                    )

                    if result.is_match:
                        label = (
                            f"{result.driver_name} "
                            f"(ID:{result.driver_id}, "
                            f"sim:{result.similarity:.2f})"
                        )
                        _draw_face_box(display, face.bbox, GREEN, label)
                        _draw_text(
                            display,
                            f"AUTHENTICATED: {result.driver_name}",
                            (10, 30),
                            GREEN,
                        )
                    else:
                        label = f"Unknown (sim:{result.similarity:.2f})"
                        _draw_face_box(display, face.bbox, RED, label)
                        _draw_text(
                            display,
                            "UNKNOWN DRIVER",
                            (10, 30),
                            RED,
                        )

                    # Log to terminal (once per second would be better in
                    # production, but fine for a prototype).
                    logger.info(
                        "Auth result: match=%s  name=%s  similarity=%.3f",
                        result.is_match,
                        result.driver_name,
                        result.similarity,
                    )

                # Show instructions at the bottom.
                h = display.shape[0]
                _draw_text(display, "Press Q to quit", (10, h - 15), WHITE, 0.5, 1)

                cv2.imshow("Driver Authentication", display)
                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    break

    except CameraError as exc:
        print(f"\nCamera error: {exc}")
        sys.exit(1)
    finally:
        cv2.destroyAllWindows()
        conn.close()

    print("\nAuthentication session ended.")


if __name__ == "__main__":
    main()
