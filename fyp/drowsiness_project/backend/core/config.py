"""
Central configuration for the NeuraDrive Driver State Intelligence System.
All tunable thresholds and parameters live here so nothing is hard-coded
deep inside the algorithm modules.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
PROJECT_ROOT = os.path.dirname(BASE_DIR)
MODEL_WEIGHTS_PATH = os.path.join(BASE_DIR, "models", "fatigue_lstm_weights.pt")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# ---------------- Camera ----------------
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
TARGET_FPS = 15  # webcams + mediapipe on CPU realistically sustain 10-20 fps

# ---------------- EAR (Eye Aspect Ratio) ----------------
EAR_THRESHOLD = 0.21          # below this the eye is considered closed

# ---------------- MAR (Mouth Aspect Ratio) / Yawn ----------------
MAR_THRESHOLD = 0.55
YAWN_MIN_DURATION_SECONDS = 1.0   # mouth must stay open this long to count as a yawn
YAWN_COOLDOWN_SECONDS = 3.0

# ---------------- Microsleep ----------------
# BOTH eyes (individually, not averaged) must be below EAR_THRESHOLD for
# this long before it counts as a microsleep. Requiring both eyes avoids a
# false trigger when only one eye is occluded/misread (e.g. head turned to
# the side), and using a duration in seconds (not a frame count) makes
# detection consistent regardless of actual camera/processing FPS.
MICROSLEEP_MIN_DURATION_SECONDS = 0.8
MICROSLEEP_COOLDOWN_SECONDS = 2.0

# ---------------- PERCLOS ----------------
# PERCLOS = % of time in a rolling window the eyes are >80% closed.
# This is the metric actually used in real automotive/aviation fatigue studies.
PERCLOS_WINDOW_SECONDS = 60
PERCLOS_WARN_THRESHOLD = 0.15   # 15% -> mild fatigue
PERCLOS_CRITICAL_THRESHOLD = 0.30  # 30% -> critical fatigue

# ---------------- Head pose ----------------
HEAD_NOD_PITCH_THRESHOLD_DEG = 20.0   # forward nod angle considered a "head drop"
HEAD_NOD_MIN_DURATION_SECONDS = 0.7
HEAD_NOD_COOLDOWN_SECONDS = 2.0

# ---------------- Fatigue fusion / KSS ----------------
# KSS = Karolinska Sleepiness Scale, 1 (extremely alert) - 9 (extremely sleepy,
# fighting sleep). Euro NCAP 2026 grades drowsiness systems against this scale,
# so we map our composite score onto it instead of inventing our own scale.
KSS_CRITICAL_THRESHOLD = 7.0
PREDICTION_HORIZON_SECONDS = 300  # "will the driver likely cross critical in
                                   # the next 5 minutes" horizon

# ---------------- Alerts ----------------
ALERT_COOLDOWN_SECONDS = 8   # don't spam the same tier repeatedly
ENABLE_SOUND_ALERTS = True
ENABLE_EMAIL_SOS = False      # set True and fill EMAIL_* below to actually send
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587
EMAIL_SENDER = "your_email@gmail.com"
EMAIL_APP_PASSWORD = "your_app_password"       # use a Gmail App Password, not your real password
EMAIL_RECEIVER = "emergency_contact@example.com"

# Simulated GPS (since we're laptop-only with no GPS hardware). Replace with a
# real GPS/geolocation source if this is ever ported to an embedded device.
SIMULATED_GPS_LAT = 28.6139
SIMULATED_GPS_LON = 77.2090

# ---------------- Runtime mode ----------------
# If no webcam is available (e.g. running headless), the system falls back to
# a synthetic frame generator so the full pipeline can still be demoed/tested.
FALLBACK_TO_SYNTHETIC_IF_NO_CAMERA = True
