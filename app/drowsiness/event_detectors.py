"""
Sustained-condition event detection, used for microsleeps, yawns, and head
nods.

Why time-based instead of frame-count-based (this replaces an earlier bug):
counting "N consecutive frames" implicitly assumes a fixed frame rate. Real
webcam + MediaPipe throughput varies by machine (CPU load, resolution,
lighting), so a fixed frame count corresponds to a different amount of real
time on different hardware -- which caused false-positive alerts in
testing. Using elapsed wall-clock seconds instead makes detection
consistent regardless of actual FPS.
"""

from app.drowsiness import config


class SustainedConditionDetector:
    def __init__(self, min_duration_seconds: float, cooldown_seconds: float = 1.0):
        self.min_duration_seconds = min_duration_seconds
        self.cooldown_seconds = cooldown_seconds
        self._condition_since = None
        self._already_counted = False
        self._last_trigger_time = -1e9
        self.count = 0

    def update(self, condition_true: bool, timestamp: float) -> bool:
        """Returns True exactly once when the condition has been continuously
        true for `min_duration_seconds`, gated by a cooldown so a single
        long event doesn't fire repeatedly every frame."""
        triggered = False

        if condition_true:
            if self._condition_since is None:
                self._condition_since = timestamp
                self._already_counted = False
            elif (not self._already_counted and
                  timestamp - self._condition_since >= self.min_duration_seconds and
                  timestamp - self._last_trigger_time >= self.cooldown_seconds):
                triggered = True
                self._already_counted = True
                self._last_trigger_time = timestamp
                self.count += 1
        else:
            self._condition_since = None
            self._already_counted = False

        return triggered

    def is_condition_active(self) -> bool:
        return self._condition_since is not None


class MicrosleepDetector(SustainedConditionDetector):
    """Detector for eye closure sustained beyond threshold duration."""

    def __init__(
        self,
        ear_threshold: float = config.EAR_THRESHOLD,
        min_duration_seconds: float = config.MICROSLEEP_MIN_DURATION_SECONDS,
        cooldown_seconds: float = config.EVENT_COOLDOWN_SECONDS,
    ):
        super().__init__(min_duration_seconds, cooldown_seconds)
        self.ear_threshold = ear_threshold

    def update(self, ear: float, now: float) -> bool:  # type: ignore[override]
        condition_true = (ear < self.ear_threshold)
        return super().update(condition_true, now)


class YawnDetector(SustainedConditionDetector):
    """Detector for mouth opening (yawn) sustained beyond threshold duration."""

    def __init__(
        self,
        mar_threshold: float = config.MAR_THRESHOLD,
        min_duration_seconds: float = config.YAWN_MIN_DURATION_SECONDS,
        cooldown_seconds: float = config.EVENT_COOLDOWN_SECONDS,
    ):
        super().__init__(min_duration_seconds, cooldown_seconds)
        self.mar_threshold = mar_threshold

    def update(self, mar: float, now: float) -> bool:  # type: ignore[override]
        condition_true = (mar > self.mar_threshold)
        return super().update(condition_true, now)


class HeadNodDetector(SustainedConditionDetector):
    """Detector for head pitching downward (nodding) sustained beyond threshold duration."""

    def __init__(
        self,
        pitch_threshold_deg: float = config.HEAD_NOD_PITCH_THRESHOLD_DEG,
        min_duration_seconds: float = config.HEAD_NOD_MIN_DURATION_SECONDS,
        cooldown_seconds: float = config.EVENT_COOLDOWN_SECONDS,
    ):
        super().__init__(min_duration_seconds, cooldown_seconds)
        self.pitch_threshold_deg = pitch_threshold_deg

    def update(self, pitch_deg: float, now: float) -> bool:  # type: ignore[override]
        condition_true = (pitch_deg < self.pitch_threshold_deg)
        return super().update(condition_true, now)
