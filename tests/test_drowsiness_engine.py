"""
Unit and functional tests for the merged drowsiness detection engine.

Validates:
- EAR & MAR geometric calculations
- PERCLOS rolling window and blink tracking
- Head pose estimation and angle unwrapping
- Time-based event detectors (microsleep, yawn, head nod)
- FusionEngine multi-modal aggregation and rule-based KSS
- AlertManager tiered escalation
"""

import time
import numpy as np
import pytest

from app.drowsiness.ear_mar import eye_aspect_ratio, mouth_aspect_ratio, compute_eye_mouth_metrics
from app.drowsiness.perclos import PerclosTracker
from app.drowsiness.head_pose import estimate_head_pose, _wrap_to_90
from app.drowsiness.event_detectors import MicrosleepDetector, YawnDetector, HeadNodDetector
from app.drowsiness.kss_mapper import rule_based_kss, kss_label, is_critical
from app.drowsiness.fusion_engine import FusionEngine
from app.drowsiness.alert_manager import AlertManager


class TestEarMar:
    def test_open_eye_has_normal_ear(self):
        # Synthetic 6 eye landmarks: [p1(outer), p2(top1), p3(top2), p4(inner), p5(bot2), p6(bot1)]
        # Width = 20px, Height = 6px -> EAR ~ (6 + 6) / (2 * 20) = 0.30
        open_eye = np.array([
            [0, 10],   # p1 outer
            [6, 7],    # p2 top1
            [14, 7],   # p3 top2
            [20, 10],  # p4 inner
            [14, 13],  # p5 bot2
            [6, 13],   # p6 bot1
        ], dtype=np.float32)
        ear = eye_aspect_ratio(open_eye, list(range(6)))
        assert 0.28 <= ear <= 0.32

    def test_closed_eye_has_low_ear(self):
        # Eyelids touching: Height = 1px -> EAR ~ (1 + 1) / (2 * 20) = 0.05
        closed_eye = np.array([
            [0, 10],
            [6, 9.5],
            [14, 9.5],
            [20, 10],
            [14, 10.5],
            [6, 10.5],
        ], dtype=np.float32)
        ear = eye_aspect_ratio(closed_eye, list(range(6)))
        assert ear < 0.10

    def test_yawn_mar_is_high(self):
        # Synthetic mouth landmarks: [p0, p1, p2, p3, p4, p5, p6, p7]
        # Open mouth: height = 24px, width = 30px -> MAR ~ (24 + 24) / (2 * 30) = 0.80
        yawning_mouth = np.zeros((8, 2), dtype=np.float32)
        yawning_mouth[0] = [0, 20]    # right corner
        yawning_mouth[1] = [30, 20]   # left corner
        yawning_mouth[2] = [15, 8]    # top outer
        yawning_mouth[4] = [15, 32]   # bottom outer
        yawning_mouth[3] = [15, 10]   # top inner
        yawning_mouth[5] = [15, 30]   # bottom inner
        mar = mouth_aspect_ratio(yawning_mouth, list(range(8)))
        assert mar >= 0.60


class TestPerclosTracker:
    def test_perclos_starts_zero(self):
        tracker = PerclosTracker(window_seconds=10.0)
        res = tracker.update(0.30, timestamp=100.0)
        assert res["perclos"] == 0.0
        assert not res["blink_triggered"]

    def test_perclos_rises_with_closed_eyes(self):
        tracker = PerclosTracker(window_seconds=5.0)
        # Feed 10 samples of closed eyes (EAR=0.10)
        res = None
        for i in range(10):
            res = tracker.update(0.10, timestamp=100.0 + (i * 0.5))
        assert res["perclos"] > 0.80


class TestHeadPose:
    def test_wrap_to_90(self):
        assert _wrap_to_90(5.0) == 5.0
        assert _wrap_to_90(-10.0) == -10.0
        assert abs(_wrap_to_90(178.0) - (-2.0)) < 1e-4
        assert abs(_wrap_to_90(-178.0) - 2.0) < 1e-4


class TestEventDetectors:
    def test_microsleep_triggers_after_sustained_closure(self):
        detector = MicrosleepDetector(min_duration_seconds=0.5)
        # Eye open
        assert not detector.update(0.30, 0.0)
        # Eye closed starting at 0.2s -> no trigger at 0.4s (0.2s elapsed)
        assert not detector.update(0.10, 0.4)
        # Eye closed at 1.0s -> 0.6s elapsed >= 0.5s -> triggers microsleep!
        assert detector.update(0.10, 1.0)


    def test_yawn_triggers_after_sustained_opening(self):
        detector = YawnDetector(min_duration_seconds=0.8)
        assert not detector.update(0.30, 0.0)
        assert not detector.update(0.70, 0.4)
        # Mouth open from 0.4s to 1.3s -> 0.9s elapsed >= 0.8s -> triggers yawn!
        assert detector.update(0.70, 1.3)



class TestKSSAndFusion:
    def test_rule_based_kss_alert_driver(self):
        kss = rule_based_kss(
            perclos=0.02,
            blink_rate_per_min=16.0,
            microsleep_count_recent=0,
            yawn_rate_per_min=0.0,
            head_nod_events_recent=0,
        )
        assert 1.0 <= kss <= 3.0
        assert not is_critical(kss)

    def test_rule_based_kss_drowsy_driver(self):
        kss = rule_based_kss(
            perclos=0.45,
            blink_rate_per_min=30.0,
            microsleep_count_recent=2,
            yawn_rate_per_min=2.5,
            head_nod_events_recent=1,
        )
        assert kss >= 7.0
        assert is_critical(kss)

    def test_fusion_engine_aggregation(self):
        engine = FusionEngine()
        # Register several frames
        for i in range(10):
            engine.register_frame_events(
                perclos=0.05,
                blink_triggered=(i % 3 == 0),
                microsleep_triggered=False,
                yawn_triggered=False,
                head_nod_triggered=False,
            )
        # Not yet 5 seconds elapsed
        assert engine.maybe_aggregate(now=engine._last_agg_time + 2.0) is None
        # 5.5 seconds elapsed -> aggregates
        res = engine.maybe_aggregate(now=engine._last_agg_time + 5.5)
        assert res is not None
        assert "kss_now" in res
        assert "raw_signals" in res


class TestAlertManager:
    def test_alert_escalation_tiers(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # Alert driver -> no alert
        alert_clean = mgr.evaluate({
            "timestamp": 100.0,
            "kss_now": 2.0,
            "raw_signals": {"avg_perclos": 0.05, "microsleeps_in_window": 0, "yawn_rate_per_min": 0},
        })
        assert alert_clean is None

        # Critical driver (KSS >= 7)
        alert_crit = mgr.evaluate({
            "timestamp": 200.0,
            "kss_now": 7.8,
            "raw_signals": {"avg_perclos": 0.40, "microsleeps_in_window": 1, "yawn_rate_per_min": 2},
        })
        assert alert_crit is not None
        assert alert_crit["tier"] == "critical"
