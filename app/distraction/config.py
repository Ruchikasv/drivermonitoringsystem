"""
Configuration parameters for driver distraction detection.

Provides tuneable thresholds for phone object detection, downward head pitch
orientation, duration gating, and alert cooldowns.
"""

import os
from app.config import settings

# ---------------------------------------------------------------------------
# Detection thresholds
# ---------------------------------------------------------------------------

# Minimum duration (seconds) of sustained phone-directed looking to confirm distraction.
# Note: Initial configurable testing threshold, not a validated safety threshold.
DISTRACTION_MIN_DURATION_SECONDS: float = float(
    os.getenv("DMS_DISTRACTION_MIN_DURATION", "2.0")
)

# Cooldown (seconds) between distraction alerts to prevent repeated beeps/incidents
# for a single prolonged continuous distraction event.
DISTRACTION_ALERT_COOLDOWN_SECONDS: float = float(
    os.getenv("DMS_DISTRACTION_COOLDOWN", "5.0")
)

# Head pitch angle (degrees, positive = downward tilt in OpenCV solvePnP camera coordinates)
# above which driver's head is considered pitched downward toward phone / lap / console area.
# Note: Frontal looking straight ahead is ~ -5.0 deg to +2.0 deg. Downward tilt is >= +6.0 deg.
DISTRACTION_PITCH_THRESHOLD_DEG: float = float(
    os.getenv("DMS_DISTRACTION_PITCH_THRESHOLD", "6.0")
)

# Iris vertical gaze ratio threshold (0.0=top eyelid, 0.5=center, 1.0=bottom eyelid).
# Values >= 0.58 indicate eye gaze is directed downward towards lower aperture/phone.
DISTRACTION_GAZE_DOWN_THRESHOLD: float = float(
    os.getenv("DMS_DISTRACTION_GAZE_THRESHOLD", "0.58")
)

# Minimum detection confidence score for phone object detector (0.0 to 1.0).
DISTRACTION_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("DMS_DISTRACTION_CONFIDENCE_THRESHOLD", "0.35")
)

# Number of consecutive evidence frames required before confirming candidate distraction.
DISTRACTION_MIN_CONSISTENT_FRAMES: int = int(
    os.getenv("DMS_DISTRACTION_MIN_CONSISTENT_FRAMES", "3")
)

# Grace period (seconds) allowing brief phone detection flicker/dropouts without
# resetting the distraction timer if head pitch remains continuously downward.
DISTRACTION_GRACE_PERIOD_SECONDS: float = float(
    os.getenv("DMS_DISTRACTION_GRACE_PERIOD", "0.4")
)

# Frame interval for running heavy object detection model (e.g. every 3 frames = 5 Hz at 15 FPS)
# to maintain real-time interactive throughput on CPU hardware.
DISTRACTION_DETECTION_INTERVAL_FRAMES: int = int(
    os.getenv("DMS_DISTRACTION_INTERVAL_FRAMES", "3")
)

# Enable audible beep notification on confirmed distraction.
ENABLE_AUDIO_BEEP: bool = (
    os.getenv("DMS_DISTRACTION_ENABLE_BEEP", "true").lower() in ("true", "1", "yes")
)

# In-cabin objects recognizable by standard pretrained COCO models (SSDLite / MobileNet / YOLO)
# Cell phone (77) is the primary target for distraction alerts.
# Other items (bottle, cup, laptop, book) are recognized for in-cabin diagnostic awareness.
CABIN_RELEVANT_COCO_CLASSES = {
    77: "cell phone",
    44: "bottle",
    47: "cup",
    73: "laptop",
    84: "book",
    1: "person",
}

