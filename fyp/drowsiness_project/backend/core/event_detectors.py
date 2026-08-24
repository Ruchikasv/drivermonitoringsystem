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
