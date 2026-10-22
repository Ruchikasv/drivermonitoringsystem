"""
Thin wrapper around MediaPipe's FaceLandmarker (Tasks API) that returns
normalized landmarks and a few pre-selected landmark groups (eyes, mouth,
nose/chin for head pose) used by the rest of the pipeline.

Note on API choice: MediaPipe's older `mp.solutions.face_mesh` API is being
phased out; current MediaPipe wheels (0.10.x, including Apple Silicon
builds) ship the Tasks API instead (`mediapipe.tasks.python.vision.
FaceLandmarker`). We use that here -- it's both the currently-maintained
API and gives us the same 468/478-point face mesh topology, so all the
landmark index constants below are unchanged from the classic FaceMesh
scheme.

The model bundle (~4 MB float16 .task file) is downloaded once on first run
into models/ and cached locally after that -- see
`_ensure_model_downloaded()`.

Integration note: _MODEL_DIR and _MODEL_PATH now read from the project-level
config adapter (app.drowsiness.config) so they resolve to the unified
models/ directory rather than the original fyp backend/models/ path.
All algorithm code is otherwise verbatim from the fyp NeuraDrive project.
"""

import os
import urllib.request

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

# Import model path from project config adapter (only change from original)
from app.drowsiness import config as _cfg

# Landmark index groups (MediaPipe Face Mesh / FaceLandmarker topology)
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
MOUTH = [61, 291, 39, 181, 0, 17, 269, 405]  # subset used for MAR
HEAD_POSE_POINTS = {
    "nose_tip": 1,
    "chin": 152,
    "left_eye_corner": 263,
    "right_eye_corner": 33,
    "left_mouth_corner": 291,
    "right_mouth_corner": 61,
}

_MODEL_DIR = _cfg.MODEL_DIR
_MODEL_PATH = _cfg.FACE_LANDMARKER_PATH
_MODEL_URL = _cfg.FACE_LANDMARKER_URL


def _ensure_model_downloaded():
    if os.path.exists(_MODEL_PATH):
        return
    os.makedirs(_MODEL_DIR, exist_ok=True)
    print(f"[face_mesh] Downloading FaceLandmarker model to {_MODEL_PATH} ...")
    try:
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
        print("[face_mesh] Download complete.")
    except Exception as e:
        raise RuntimeError(
            "Could not auto-download the MediaPipe FaceLandmarker model "
            f"(needs internet access on first run). Error: {e}\n"
            f"Manual fix: download {_MODEL_URL} and save it to {_MODEL_PATH}"
        )


class FaceMeshDetector:
    def __init__(self, max_faces: int = 1, min_detection_conf: float = 0.5,
                 min_tracking_conf: float = 0.5):
        _ensure_model_downloaded()
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=max_faces,
            min_face_detection_confidence=min_detection_conf,
            min_tracking_confidence=min_tracking_conf,
            min_face_presence_confidence=min_detection_conf,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)
        self._frame_index = 0

    def process(self, frame_bgr: np.ndarray):
        """
        Returns (landmarks_px, landmarks_norm): landmarks_px is an (N, 2)
        array of pixel coords, landmarks_norm is (N, 3) normalized (x,y,z),
        or (None, None) if no face is found.
        """
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # VIDEO mode requires monotonically increasing timestamps (ms)
        timestamp_ms = self._frame_index * 33
        self._frame_index += 1

        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        if not result.face_landmarks:
            return None, None

        landmarks = result.face_landmarks[0]
        pts_norm = np.array([[lm.x, lm.y, lm.z] for lm in landmarks])
        pts_px = np.array([[lm.x * w, lm.y * h] for lm in landmarks])
        return pts_px, pts_norm

    def close(self):
        self.landmarker.close()


def crop_eye(frame: np.ndarray, pts_px: np.ndarray, eye_indices: list, padding: float = 0.4):
    """Calculate bounding box for eye landmarks, apply padding, and crop."""
    eye_pts = pts_px[eye_indices]
    x_min = np.min(eye_pts[:, 0])
    x_max = np.max(eye_pts[:, 0])
    y_min = np.min(eye_pts[:, 1])
    y_max = np.max(eye_pts[:, 1])
    
    w = x_max - x_min
    h = y_max - y_min
    
    cx = x_min + w / 2
    cy = y_min + h / 2
    
    # Make it square with padding
    side = max(w, h) * (1 + padding)
    
    x1 = int(cx - side / 2)
    y1 = int(cy - side / 2)
    x2 = int(cx + side / 2)
    y2 = int(cy + side / 2)
    
    # Clip to frame boundaries
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(frame.shape[1], x2)
    y2 = min(frame.shape[0], y2)
    
    crop = frame[y1:y2, x1:x2]
    rect = (x1, y1, x2, y2)
    return crop, rect

def draw_landmarks(frame: np.ndarray, pts_px: np.ndarray, color=(0, 255, 0), radius=1):
    """Draw face landmarks on the frame."""
    for pt in pts_px:
        cv2.circle(frame, (int(pt[0]), int(pt[1])), radius, color, -1)

