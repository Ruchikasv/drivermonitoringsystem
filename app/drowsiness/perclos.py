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
        self._blink_timestamps = deque()  # timestamps of blinks for rolling rate
        self.blink_count = 0
        self._was_closed = False

    def update(self, ear_value: float, timestamp: float = None, face_detected: bool = True) -> dict:
        if timestamp is None:
            timestamp = time.time()

        # If face is lost, do NOT assume eyes are closed
        if not face_detected:
            is_closed = False
        else:
            is_closed = (ear_value < self.ear_threshold)

        self._samples.append((timestamp, is_closed))
        self._prune(timestamp)

        blink_triggered = self._was_closed and not is_closed
        if blink_triggered:
            self.blink_count += 1
            self._blink_timestamps.append(timestamp)
        self._was_closed = is_closed

        return {
            "perclos": self.current_perclos(),
            "is_eye_closed": is_closed,
            "blink_triggered": blink_triggered,
            "blink_count_session": self.blink_count,
            "blink_rate_per_min": self.current_blink_rate(timestamp),
            "is_warming_up": self.is_warming_up(),
        }

    def _prune(self, now: float):
        cutoff = now - self.window_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()
        while self._blink_timestamps and self._blink_timestamps[0] < cutoff:
            self._blink_timestamps.popleft()

    def is_warming_up(self) -> bool:
        if not self._samples:
            return True
        time_span = self._samples[-1][0] - self._samples[0][0]
        warmup_limit = min(self.window_seconds, 15.0)
        return time_span < warmup_limit

    def current_perclos(self) -> float:
        if not self._samples:
            return 0.0

        time_span = self._samples[-1][0] - self._samples[0][0]
        closed_count = sum(1 for _, c in self._samples if c)
        total_count = len(self._samples)

        if total_count == 0:
            return 0.0

        # When window is warming up, scale ratio against warmup baseline to prevent early false spikes from a single blink
        warmup_limit = min(self.window_seconds, 20.0)
        if time_span < warmup_limit:
            raw_ratio = closed_count / total_count
            warmup_factor = max(time_span, 1.0) / warmup_limit
            return round(raw_ratio * warmup_factor, 4)

        return round(closed_count / total_count, 4)

    def current_blink_rate(self, now: float = None) -> float:
        now = now or time.time()
        self._prune(now)
        if not self._samples:
            return 16.0  # default normal baseline
        time_span = max(1.0, self._samples[-1][0] - self._samples[0][0])
        minutes = time_span / 60.0
        return round(len(self._blink_timestamps) / max(minutes, 1e-4), 1)
