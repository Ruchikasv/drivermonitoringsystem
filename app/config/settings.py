"""
Centralised configuration for the Driver Monitoring System.

All tuneable parameters live here so they can be adjusted in one place
rather than being scattered across modules.  In Phase 2 these values
may be overridden by environment variables or a .env file.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Project root is two levels above this file (app/config/settings.py → project root)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# Directory where the SQLite database file is stored.
DATA_DIR: Path = PROJECT_ROOT / "data"

# SQLite database file path.
DATABASE_PATH: Path = DATA_DIR / "drivers.db"

# Directory where InsightFace model weights are cached.
# Explicitly set to avoid issues with spaces in the workspace path.
MODEL_DIR: Path = PROJECT_ROOT / "models"

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

# Index of the webcam device (0 = default built-in camera).
CAMERA_INDEX: int = int(os.getenv("DMS_CAMERA_INDEX", "0"))

# ---------------------------------------------------------------------------
# Face Recognition — InsightFace / ArcFace
# ---------------------------------------------------------------------------

# InsightFace model pack name.
# "buffalo_l" = large (best accuracy, ~300 MB).
# "buffalo_s" = small (faster, lower accuracy, ~100 MB).
INSIGHTFACE_MODEL_NAME: str = os.getenv("DMS_MODEL_NAME", "buffalo_l")

# Detection confidence threshold — faces with scores below this are ignored.
DETECTION_CONFIDENCE: float = float(os.getenv("DMS_DETECTION_CONFIDENCE", "0.5"))

# Recognition similarity threshold.
# Cosine similarity above this → positive match.
# Typical same-person scores: 0.5–0.8; different-person scores: 0.0–0.3.
# Starting at 0.45 as a conservative default — tune after real-world testing.
RECOGNITION_THRESHOLD: float = float(os.getenv("DMS_RECOGNITION_THRESHOLD", "0.45"))

# Dimensionality of ArcFace embeddings (do not change unless switching models).
EMBEDDING_DIM: int = 512

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Number of good-quality frames to capture during driver registration.
REGISTRATION_NUM_FRAMES: int = int(os.getenv("DMS_REG_FRAMES", "10"))

# Minimum number of successful embeddings required to proceed with registration.
REGISTRATION_MIN_FRAMES: int = int(os.getenv("DMS_REG_MIN_FRAMES", "5"))

# Delay in seconds between capture frames (allows slight pose variation).
REGISTRATION_FRAME_DELAY: float = float(os.getenv("DMS_REG_DELAY", "0.3"))

# Similarity threshold for the duplicate-driver check during registration.
# If a new enrollment embedding is this similar to an existing driver,
# a warning is issued.
DUPLICATE_DETECTION_THRESHOLD: float = float(
    os.getenv("DMS_DUPLICATE_THRESHOLD", "0.55")
)

# ---------------------------------------------------------------------------
# Drowsiness Detection Engine (Phase 2+)
# ---------------------------------------------------------------------------

# MediaPipe FatigueLSTM trained weights.
FATIGUE_LSTM_PATH: Path = MODEL_DIR / "fatigue_lstm_weights.pt"

# MediaPipe FaceLandmarker .task bundle.
FACE_LANDMARKER_PATH: Path = MODEL_DIR / "face_landmarker.task"

# Directory where drowsiness evidence screenshots are stored.
EVIDENCE_DIR: Path = DATA_DIR / "evidence"

# Target camera FPS for the monitoring WebSocket loop.
MONITORING_FPS: int = int(os.getenv("DMS_MONITORING_FPS", "15"))
