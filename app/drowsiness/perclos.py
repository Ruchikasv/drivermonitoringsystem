"""
PERCLOS (PERcentage of eye CLOSure) and blink-rate tracker.

PERCLOS is the metric actually validated in real fatigue research (NHTSA /
FHWA driver fatigue studies use it as ground truth) -- the percentage of a
rolling time window during which the eyes are substantially closed. Using
the *average* of both eyes here is appropriate for PERCLOS specifically,
since it's a smoothed percentage-of-time measure, not a single-frame
trigger.

Note: microsleep detection is handled separately, in
`event_detectors.SustainedConditionDetector`, using BOTH eyes' individual
EAR (not the average) so a single occluded/misread eye during a head turn
can't falsely trigger a "microsleep" alert on its own -- see app.py.
"""

import time
from collections import deque
from app.drowsiness import config


class PerclosTracker:
    def __init__(self, ear_threshold: float = config.EAR_THRESHOLD, window_seconds: float = 60.0):
        self.ear_threshold = ear_threshold
        self.window_seconds = window_seconds


        self._samples = deque()  # (timestamp, is_closed: bool)
        self.blink_count = 0
        self._was_closed = False

    def update(self, ear_value: float, timestamp: float = None) -> dict:
        if timestamp is None:
            timestamp = time.time()

        is_closed = ear_value < self.ear_threshold
        self._samples.append((timestamp, is_closed))
        self._prune(timestamp)

        blink_triggered = self._was_closed and not is_closed
        if blink_triggered:
            self.blink_count += 1
        self._was_closed = is_closed

        return {
            "perclos": self.current_perclos(),
            "is_eye_closed": is_closed,
            "blink_triggered": blink_triggered,
            "blink_count_session": self.blink_count,
        }

    def _prune(self, now: float):
        cutoff = now - self.window_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def current_perclos(self) -> float:
        if not self._samples:
            return 0.0
        closed = sum(1 for _, c in self._samples if c)
        return closed / len(self._samples)
