"""
Configuration adapter for the drowsiness detection engine.

Exposes the same constant names that the original fyp core/config.py used,
but sources them from the current project's settings.py and environment
variables.  This keeps all algorithm modules (ear_mar, perclos, etc.)
importable without modification while allowing the merged project to
configure thresholds from one central place.
"""

import os
from pathlib import Path

from app.config import settings

# ---------------------------------------------------------------------------
# Model paths
# ---------------------------------------------------------------------------

# MediaPipe FaceLandmarker .task bundle (downloaded once on first run).
MODEL_DIR: str = str(settings.MODEL_DIR)
MODEL_WEIGHTS_PATH: str = str(settings.MODEL_DIR / "fatigue_lstm_weights.pt")
FACE_LANDMARKER_PATH: str = str(settings.MODEL_DIR / "face_landmarker.task")

# MediaPipe model download URL (used by face_mesh.py _ensure_model_downloaded)
FACE_LANDMARKER_URL: str = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)

# ---------------------------------------------------------------------------
# Eye / mouth thresholds
# ---------------------------------------------------------------------------

# Eye Aspect Ratio below this → eye considered closed.
# Calibrated for the Soukupova & Cech (2016) formula on MediaPipe landmarks.
EAR_THRESHOLD: float = float(os.getenv("DMS_EAR_THRESHOLD", "0.21"))

# Mouth Aspect Ratio above this → yawn detected.
MAR_THRESHOLD: float = float(os.getenv("DMS_MAR_THRESHOLD", "0.55"))

# ---------------------------------------------------------------------------
# PERCLOS
# ---------------------------------------------------------------------------

# Rolling window duration for PERCLOS calculation (seconds).
PERCLOS_WINDOW_SECONDS: float = float(os.getenv("DMS_PERCLOS_WINDOW", "60.0"))

# PERCLOS fraction above which the system starts scoring KSS critically.
PERCLOS_CRITICAL_THRESHOLD: float = float(os.getenv("DMS_PERCLOS_CRITICAL", "0.40"))

# PERCLOS fraction above which the system emits a "nudge" alert.
PERCLOS_WARN_THRESHOLD: float = float(os.getenv("DMS_PERCLOS_WARN", "0.15"))

# ---------------------------------------------------------------------------
# Event durations (seconds) — time-based, not frame-count-based
# ---------------------------------------------------------------------------

# Both eyes must be closed for at least this long to trigger a microsleep.
# Normal blinks are 0.15s - 0.35s; 1.5s requires genuine prolonged closure.
MICROSLEEP_MIN_DURATION_SECONDS: float = float(os.getenv("DMS_MICROSLEEP_DURATION", "1.5"))

# Mouth must be open past MAR_THRESHOLD for this long to count as a yawn.
YAWN_MIN_DURATION_SECONDS: float = float(os.getenv("DMS_YAWN_DURATION", "1.5"))

# Head pitch below HEAD_NOD_PITCH_THRESHOLD_DEG for this long → head nod.
HEAD_NOD_MIN_DURATION_SECONDS: float = float(os.getenv("DMS_HEAD_NOD_DURATION", "1.0"))

# Head pitch angle (degrees, negative = downward tilt) indicating a head nod.
HEAD_NOD_PITCH_THRESHOLD_DEG: float = float(os.getenv("DMS_HEAD_NOD_PITCH", "-15.0"))

# Cooldown between event triggers of the same type (seconds).
EVENT_COOLDOWN_SECONDS: float = float(os.getenv("DMS_EVENT_COOLDOWN", "1.5"))

# ---------------------------------------------------------------------------
# KSS / Alert
# ---------------------------------------------------------------------------

# KSS score at or above which a CRITICAL alert fires.
# Euro NCAP's 2026 protocol classifies KSS >= 7 as drowsy.
KSS_CRITICAL_THRESHOLD: float = float(os.getenv("DMS_KSS_CRITICAL", "7.0"))

# Per-tier alert cooldown (seconds) — prevents alert spam.
ALERT_COOLDOWN_SECONDS: float = float(os.getenv("DMS_ALERT_COOLDOWN", "8.0"))

# ---------------------------------------------------------------------------
# LSTM / Fusion
# ---------------------------------------------------------------------------

# Prediction horizon for p_critical_soon (seconds).
PREDICTION_HORIZON_SECONDS: float = float(os.getenv("DMS_PREDICTION_HORIZON", "300.0"))

# ---------------------------------------------------------------------------
# Incident log (legacy flat-file path — kept for AlertManager compatibility,
# but the merged system writes incidents to SQLite instead)
# ---------------------------------------------------------------------------

LOG_DIR: str = str(settings.DATA_DIR / "logs")
INCIDENTS_LOG_PATH: str = str(settings.DATA_DIR / "logs" / "incidents.jsonl")

# ---------------------------------------------------------------------------
# Evidence screenshots
# ---------------------------------------------------------------------------

EVIDENCE_DIR: str = str(settings.DATA_DIR / "evidence")

# ---------------------------------------------------------------------------
# Email / SOS (disabled by default — enable via env vars)
# ---------------------------------------------------------------------------

ENABLE_EMAIL_SOS: bool = os.getenv("DMS_ENABLE_EMAIL_SOS", "false").lower() == "true"
EMAIL_SENDER: str = os.getenv("DMS_EMAIL_SENDER", "")
EMAIL_RECEIVER: str = os.getenv("DMS_EMAIL_RECEIVER", "")
EMAIL_APP_PASSWORD: str = os.getenv("DMS_EMAIL_APP_PASSWORD", "")
EMAIL_SMTP_SERVER: str = os.getenv("DMS_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT: int = int(os.getenv("DMS_SMTP_PORT", "587"))

# Simulated GPS coordinates (no GPS hardware on laptop).
SIMULATED_GPS_LAT: float = float(os.getenv("DMS_GPS_LAT", "12.9716"))
SIMULATED_GPS_LON: float = float(os.getenv("DMS_GPS_LON", "77.5946"))
