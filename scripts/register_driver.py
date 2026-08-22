#!/usr/bin/env python
"""
Register a new driver via the laptop webcam.

Usage::

    python -m scripts.register_driver

The script will:
1. Prompt for the driver's name.
2. Open the webcam and show a live preview with face bounding boxes.
3. Capture multiple frames when the user presses SPACE.
4. Average the embeddings and store the driver in the database.
"""

from __future__ import annotations

import logging
import sys
import time

import cv2
import numpy as np

# Add project root to path so we can import app.* when run as a script.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from app.camera.capture import CameraError, WebcamCapture
from app.config import settings
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.face_recognition.comparator import (
    average_embeddings,
    cosine_similarity,
)
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


def _draw_status(
    frame: np.ndarray,
    text: str,
    colour: tuple[int, int, int] = GREEN,
) -> None:
    """Draw a status message at the top of the frame."""
    cv2.putText(
        frame, text, (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2,
    )


def _draw_face_box(
    frame: np.ndarray,
    bbox: np.ndarray,
    colour: tuple[int, int, int] = GREEN,
) -> None:
    """Draw a bounding box around a detected face."""
    x1, y1, x2, y2 = bbox
    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), colour, 2)


def main() -> None:
    # --- 1. Get driver name --------------------------------------------------
    print("\n" + "=" * 50)
    print("  DRIVER REGISTRATION")
    print("=" * 50)
    name = input("\nEnter driver name: ").strip()
    if not name:
        print("Error: Name cannot be empty.")
        sys.exit(1)

    # --- 2. Set up database --------------------------------------------------
    conn = get_connection()
    init_db(conn)
    repo = DriverRepository(conn)

    # --- 3. Set up face detector ---------------------------------------------
    detector = FaceDetector()

    # --- 4. Open webcam and collect embeddings --------------------------------
    print(f"\nOpening webcam (index {settings.CAMERA_INDEX}) …")
    print("Press SPACE to start capturing face samples.")
    print("Press Q to cancel.\n")

    embeddings: list[np.ndarray] = []
    target_frames = settings.REGISTRATION_NUM_FRAMES
    min_frames = settings.REGISTRATION_MIN_FRAMES

    try:
        with WebcamCapture() as cam:
            capturing = False
            frames_captured = 0

            while True:
                frame = cam.read_frame()
                display = frame.copy()

                # Detect faces in this frame.
                faces = detector.detect_faces(frame)

                if len(faces) == 0:
                    _draw_status(display, "No face detected", RED)
                elif len(faces) > 1:
                    _draw_status(
                        display,
                        f"Multiple faces ({len(faces)}) — need exactly 1",
                        RED,
                    )
                    for f in faces:
                        _draw_face_box(display, f.bbox, RED)
                else:
                    face = faces[0]
                    _draw_face_box(display, face.bbox, GREEN)

                    if capturing:
                        embeddings.append(face.embedding.copy())
                        frames_captured += 1
                        _draw_status(
                            display,
                            f"Capturing … {frames_captured}/{target_frames}",
                            YELLOW,
                        )

                        if frames_captured >= target_frames:
                            break

                        time.sleep(settings.REGISTRATION_FRAME_DELAY)
                    else:
                        _draw_status(
                            display,
                            f"Face detected (conf: {face.score:.2f}). Press SPACE to capture.",
                            GREEN,
                        )

                cv2.imshow("Driver Registration", display)
                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    print("\nRegistration cancelled.")
                    cv2.destroyAllWindows()
                    conn.close()
                    sys.exit(0)
                elif key == ord(" ") and not capturing:
                    capturing = True
                    print("Capturing face samples …")

    except CameraError as exc:
        print(f"\nCamera error: {exc}")
        conn.close()
        sys.exit(1)
    finally:
        cv2.destroyAllWindows()

    # --- 5. Validate collected embeddings ------------------------------------
    if len(embeddings) < min_frames:
        print(
            f"\nError: Only captured {len(embeddings)} good frames "
            f"(minimum required: {min_frames}). Registration aborted."
        )
        conn.close()
        sys.exit(1)

    print(f"\nCaptured {len(embeddings)} face samples successfully.")

    # --- 6. Average and normalise embeddings ---------------------------------
    avg_embedding = average_embeddings(embeddings)
    logger.info(
        "Average embedding: shape=%s, norm=%.4f",
        avg_embedding.shape,
        np.linalg.norm(avg_embedding),
    )

    # --- 7. Check for duplicate drivers --------------------------------------
    existing_drivers = repo.get_all_drivers()
    for driver in existing_drivers:
        sim = cosine_similarity(avg_embedding, driver.face_embedding)
        if sim >= settings.DUPLICATE_DETECTION_THRESHOLD:
            print(
                f"\n⚠  WARNING: This face is similar to existing driver "
                f"'{driver.name}' (ID: {driver.driver_id}, "
                f"similarity: {sim:.3f})."
            )
            confirm = input("Continue registration anyway? (y/N): ").strip().lower()
            if confirm != "y":
                print("Registration cancelled.")
                conn.close()
                sys.exit(0)
            break  # Only warn for the closest match.

    # --- 8. Save to database -------------------------------------------------
    driver_id = repo.add_driver(name, avg_embedding)
    conn.close()

    print("\n" + "=" * 50)
    print("  REGISTRATION SUCCESSFUL")
    print("=" * 50)
    print(f"  Driver ID   : {driver_id}")
    print(f"  Name        : {name}")
    print(f"  Samples used: {len(embeddings)}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
