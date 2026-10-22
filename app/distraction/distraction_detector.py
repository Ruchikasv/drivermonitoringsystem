"""
Driver Visual Distraction Detection Engine.

Implements sustained-condition tracking for phone-related visual distraction.

Core Logic:
1. Candidate Distraction Condition:
   A driver is in candidate distraction ONLY when:
   - Trip is ACTIVE (not paused or ended)
   - Face is DETECTED
   - Eyes are OPEN (EAR >= threshold, differentiating from microsleep/nodding off)
   - Phone is DETECTED in the vehicle cabin (confidence >= threshold)
   - Driver's head pitch is TILTED DOWNWARD toward the phone / lap / center console
     (pitch <= DISTRACTION_PITCH_THRESHOLD_DEG)

2. Duration and Consistency Verification:
   - Initial configurable testing threshold: 2.0 seconds (DISTRACTION_MIN_DURATION_SECONDS).
   - Brief glances (< 2.0s) do not trigger an alarm.
   - Requires multiple consecutive evidence frames (DISTRACTION_MIN_CONSISTENT_FRAMES)
     to avoid transient false positives.
   - Grace period (DISTRACTION_GRACE_PERIOD_SECONDS) accommodates temporary 1-2 frame
     detection dropouts if downward posture is maintained.

3. Alert, Cooldown, and Recovery:
   - Confirmed event triggers an alarm / beep exactly once per incident.
   - Cooldown period prevents alarm repetition every frame while distraction continues.
   - When the driver looks back toward the road or phone is put away, the active
     distraction timer resets immediately to 0.0s.

4. Drowsiness Engine Isolation:
   - Operates independently from microsleep, yawn, head-nod, and PERCLOS engines.
   - Does not reset or alter drowsiness fatigue tracking.
"""

import logging
import time
from typing import Optional, Dict, Any, Tuple
from collections import deque
import numpy as np

from app.distraction import config
from app.distraction.gaze import estimate_gaze_ratios, is_driver_looking_at_phone

logger = logging.getLogger(__name__)


class PhoneDistractionDetector:
    """Detects prolonged visual distraction caused by looking at a mobile phone."""

    def __init__(
        self,
        min_duration_seconds: float = config.DISTRACTION_MIN_DURATION_SECONDS,
        cooldown_seconds: float = config.DISTRACTION_ALERT_COOLDOWN_SECONDS,
        pitch_threshold_deg: float = config.DISTRACTION_PITCH_THRESHOLD_DEG,
        confidence_threshold: float = config.DISTRACTION_CONFIDENCE_THRESHOLD,
        min_consistent_frames: int = config.DISTRACTION_MIN_CONSISTENT_FRAMES,
        grace_period_seconds: float = config.DISTRACTION_GRACE_PERIOD_SECONDS,
        ear_threshold: float = 0.20,
        gaze_down_threshold: float = config.DISTRACTION_GAZE_DOWN_THRESHOLD,
    ):
        self.min_duration_seconds = min_duration_seconds
        self.cooldown_seconds = cooldown_seconds
        self.pitch_threshold_deg = pitch_threshold_deg
        self.confidence_threshold = confidence_threshold
        self.min_consistent_frames = min_consistent_frames
        self.grace_period_seconds = grace_period_seconds
        self.ear_threshold = ear_threshold
        self.gaze_down_threshold = gaze_down_threshold

        # Active episode state
        self._distraction_start_time: Optional[float] = None
        self._last_evidence_time: Optional[float] = None
        self._consecutive_evidence_frames: int = 0
        self._is_sustained: bool = False
        self._already_alerted: bool = False
        self._incident_logged: bool = False

        # Alert cooldown & tracking
        self._last_trigger_time: float = -1e9
        self.total_incidents: int = 0
        self._incident_timestamps: deque = deque(maxlen=50)

    def reset(self) -> None:
        """
        Completely reset all detector states, pending timers, and counters.
        Must be invoked on trip pause, trip end, and trip start/resume.
        """
        self._distraction_start_time = None
        self._last_evidence_time = None
        self._consecutive_evidence_frames = 0
        self._is_sustained = False
        self._already_alerted = False
        self._incident_logged = False
        self._last_trigger_time = -1e9

    def reset_active_glance(self) -> None:
        """
        Reset active glance duration when driver returns attention to the road,
        retaining cooldown history to prevent immediate alert bouncing.
        """
        self._distraction_start_time = None
        self._last_evidence_time = None
        self._consecutive_evidence_frames = 0
        self._is_sustained = False
        self._already_alerted = False
        self._incident_logged = False
        self._last_trigger_time = -1e9

    def update(
        self,
        now: Optional[float] = None,
        phone_detected: bool = False,
        phone_confidence: float = 0.0,
        phone_box: Optional[Tuple[int, int, int, int]] = None,
        head_pitch_deg: float = 0.0,
        face_detected: bool = True,
        ear: float = 0.30,
        is_trip_active: bool = True,
        gaze_info: Optional[Dict[str, Any]] = None,
        landmarks_px: Optional[np.ndarray] = None,
        gaze_vert_ratio: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate single-frame multimodal telemetry for phone visual distraction.

        Returns:
            Dict containing real-time distraction metrics and alert triggers.
        """
        now = now if now is not None else time.time()

        if gaze_info is None and gaze_vert_ratio is not None:
            gaze_info = {
                "vert_ratio": float(gaze_vert_ratio),
                "is_gaze_down": float(gaze_vert_ratio) >= self.gaze_down_threshold,
                "valid": True,
                "gaze_direction": "down" if float(gaze_vert_ratio) >= self.gaze_down_threshold else "center",
            }


        # 1. Trip State Rule: If trip is not actively running, suspend and reset.
        if not is_trip_active:
            self.reset()
            return {
                "distraction_active": False,
                "distraction_confirmed": False,
                "triggered": False,
                "is_new_incident": False,
                "duration_seconds": 0.0,
                "cooldown_active": False,
                "looking_down": False,
                "phone_present": False,
                "distraction_type": "phone",
                "looking_reason": "Trip not active",
                "gaze_vert_ratio": 0.50,
                "gaze_direction": "unknown",
            }

        # 2. Face Loss Rule: If face tracking is lost, reset active glance
        if not face_detected:
            self.reset_active_glance()
            return {
                "distraction_active": False,
                "distraction_confirmed": False,
                "triggered": False,
                "is_new_incident": False,
                "duration_seconds": 0.0,
                "cooldown_active": (now - self._last_trigger_time) < self.cooldown_seconds,
                "looking_down": False,
                "phone_present": False,
                "distraction_type": "phone",
                "looking_reason": "Face tracking unavailable",
                "gaze_vert_ratio": 0.50,
                "gaze_direction": "unknown",
            }

        # 3. Geometric & Multimodal Evidence Evaluation
        if gaze_info is None and landmarks_px is not None:
            gaze_info = estimate_gaze_ratios(landmarks_px)

        is_looking, looking_reason = is_driver_looking_at_phone(
            head_pitch_deg=head_pitch_deg,
            gaze_info=gaze_info or {},
            phone_box=phone_box,
            landmarks_px=landmarks_px,
            pitch_down_threshold=self.pitch_threshold_deg,
            gaze_down_threshold=self.gaze_down_threshold,
            ear=ear,
            ear_threshold=self.ear_threshold,
        )

        phone_present = phone_detected and (phone_confidence >= self.confidence_threshold)

        # CRITICAL SAFETY RULE: A visible phone alone NEVER triggers distraction.
        # Both verified looking orientation AND phone presence are required.
        candidate_active = is_looking and phone_present

        # 4. Temporal Evidence Tracking with Dropout Grace Period
        current_duration = 0.0
        triggered = False
        is_new_incident = False

        if candidate_active:
            self._consecutive_evidence_frames += 1
            self._last_evidence_time = now

            if self._distraction_start_time is None:
                self._distraction_start_time = now
                current_duration = 0.0
            else:
                current_duration = max(0.0, now - self._distraction_start_time)

        elif self._distraction_start_time is not None:
            # Check if temporary frame dropout is within grace period while head/gaze is still down
            within_grace = (
                self._last_evidence_time is not None
                and (now - self._last_evidence_time <= self.grace_period_seconds)
                and is_looking
            )
            if within_grace:
                current_duration = max(0.0, now - self._distraction_start_time)
            else:
                # Driver looked back up or condition broken -> RECOVERY
                self.reset_active_glance()
                current_duration = 0.0

        # 5. Distraction Confirmation & Alert Evaluation
        # Must meet duration threshold AND minimum consistent frames
        has_min_duration = current_duration >= self.min_duration_seconds
        has_min_consistency = self._consecutive_evidence_frames >= self.min_consistent_frames
        is_confirmed = has_min_duration and has_min_consistency

        cooldown_ok = (now - self._last_trigger_time) >= self.cooldown_seconds

        if is_confirmed:
            self._is_sustained = True
            # Exactly one incident recorded per continuous distraction episode
            if not self._incident_logged:
                is_new_incident = True
                self._incident_logged = True
                self._already_alerted = True
                self.total_incidents += 1
                self._incident_timestamps.append(now)
                logger.warning(
                    "Confirmed driver phone distraction! Sustained: %.2fs, Head Pitch: %.1f deg",
                    current_duration,
                    head_pitch_deg,
                )

            # Beep repeats at configurable interval (cooldown_seconds) while distraction continues
            if cooldown_ok:
                triggered = True
                self._last_trigger_time = now
                logger.info(
                    "Distraction beep triggered! Sustained: %.2fs, repeating every %.1fs",
                    current_duration,
                    self.cooldown_seconds,
                )
        else:
            self._is_sustained = False

        cooldown_active = (now - self._last_trigger_time) < self.cooldown_seconds

        gaze_dict = gaze_info or {}
        return {
            "distraction_active": candidate_active or (self._distraction_start_time is not None),
            "distraction_confirmed": self._is_sustained,
            "triggered": triggered,
            "is_new_incident": is_new_incident,
            "duration_seconds": round(current_duration, 2),
            "cooldown_active": cooldown_active,
            "looking_down": is_looking,
            "looking_reason": looking_reason,
            "gaze_vert_ratio": gaze_dict.get("vert_ratio", 0.50),
            "gaze_direction": gaze_dict.get("gaze_direction", "unknown"),
            "is_gaze_down": gaze_dict.get("is_gaze_down", False),
            "head_pitch_down": head_pitch_deg >= self.pitch_threshold_deg,
            "phone_present": phone_present,
            "distraction_type": "phone",
        }
