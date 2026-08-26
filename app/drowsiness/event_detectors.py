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

from collections import deque
from app.drowsiness import config


class SustainedConditionDetector:
    def __init__(self, min_duration_seconds: float, cooldown_seconds: float = 1.0):
        self.min_duration_seconds = min_duration_seconds
        self.cooldown_seconds = cooldown_seconds
        self._condition_since = None
        self._is_sustained = False
        self._already_counted = False
        self._last_trigger_time = -1e9
        self.count = 0
        self._event_timestamps = deque(maxlen=50)

    def update(self, condition_true: bool, timestamp: float, face_detected: bool = True) -> bool:
        """Returns True exactly once when the condition has been continuously
        true for `min_duration_seconds`, gated by a cooldown so a single
        long event doesn't fire repeatedly every frame."""
        triggered = False

        if not face_detected:
            self._condition_since = None
            self._is_sustained = False
            self._already_counted = False
            return False

        if condition_true:
            if self._condition_since is None:
                self._condition_since = timestamp
                self._is_sustained = False
                self._already_counted = False
            elif timestamp - self._condition_since >= self.min_duration_seconds:
                self._is_sustained = True
                if not self._already_counted and (timestamp - self._last_trigger_time >= self.cooldown_seconds):
                    triggered = True
                    self._already_counted = True
                    self._last_trigger_time = timestamp
                    self.count += 1
                    self._event_timestamps.append(timestamp)
        else:
            self._condition_since = None
            self._is_sustained = False
            self._already_counted = False

        return triggered

    def is_condition_active(self) -> bool:
        """Returns True ONLY if the condition has been continuously active for at least min_duration_seconds."""
        return self._is_sustained

    def get_sustained_duration(self, now: float) -> float:
        """Returns the continuous duration in seconds that this condition has been true."""
        if self._condition_since is None:
            return 0.0
        return max(0.0, now - self._condition_since)

    def get_recent_count(self, now: float, window_seconds: float = 60.0) -> int:
        """Returns the count of triggers occurring within the recent rolling time window."""
        cutoff = now - window_seconds
        while self._event_timestamps and self._event_timestamps[0] < cutoff:
            self._event_timestamps.popleft()
        return len(self._event_timestamps)

    def reset_condition(self):
        """Immediately reset active condition tracker."""
        self._condition_since = None
        self._is_sustained = False
        self._already_counted = False


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

    def update(self, ear: float, now: float, face_detected: bool = True) -> bool:  # type: ignore[override]
        condition_true = (ear < self.ear_threshold) and face_detected
        return super().update(condition_true, now, face_detected=face_detected)


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

    def update(self, mar: float, now: float, face_detected: bool = True) -> bool:  # type: ignore[override]
        condition_true = (mar > self.mar_threshold) and face_detected
        return super().update(condition_true, now, face_detected=face_detected)


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

    def update(self, pitch_deg: float, now: float, face_detected: bool = True) -> bool:  # type: ignore[override]
        condition_true = (pitch_deg < self.pitch_threshold_deg) and face_detected
        return super().update(condition_true, now, face_detected=face_detected)
