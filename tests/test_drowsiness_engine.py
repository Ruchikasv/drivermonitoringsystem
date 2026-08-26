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

    def test_normal_blink_does_not_trigger_microsleep(self):
        # Default microsleep requires 1.5s
        detector = MicrosleepDetector()
        # Normal blink: eyes close for 0.25s (from t=0.1s to t=0.35s)
        assert not detector.update(0.30, 0.0)
        assert not detector.update(0.10, 0.10)
        assert not detector.is_condition_active()  # Condition is NOT active/sustained yet!
        assert not detector.update(0.10, 0.35)
        assert not detector.is_condition_active()
        # Eye opens again at t=0.40s
        assert not detector.update(0.30, 0.40)
        assert not detector.is_condition_active()

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
    def test_normal_awake_driver_produces_no_alert(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # Awake driver (EAR 0.30, PERCLOS 5%, KSS 1.5, Pitch -2 deg)
        alert = mgr.evaluate({
            "timestamp": 100.0,
            "face_detected": True,
            "kss_now": 1.5,
            "ear": 0.30,
            "mar": 0.28,
            "pitch": -2.0,
            "sustained_eye_closure_seconds": 0.0,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.05, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
        })
        assert alert is None

    def test_moderate_kss_alone_never_triggers_level_3(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # Moderate KSS (5.1 or 5.8) with awake eyes (EAR 0.30)
        for kss in [5.1, 5.8, 6.2]:
            alert = mgr.evaluate({
                "timestamp": 100.0 + kss,
                "face_detected": True,
                "kss_now": kss,
                "ear": 0.30,
                "mar": 0.29,
                "pitch": -3.0,
                "sustained_eye_closure_seconds": 0.0,
                "sustained_yawn_seconds": 0.0,
                "sustained_nod_seconds": 0.0,
                "raw_signals": {"avg_perclos": 0.12, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
            })
            assert alert is None or alert["tier"] != "critical"

    def test_moderate_perclos_alone_never_triggers_level_3(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # PERCLOS 21.4% or 27.2% with open eyes (EAR 0.32)
        for p in [0.214, 0.272]:
            alert = mgr.evaluate({
                "timestamp": 100.0 + (p * 10),
                "face_detected": True,
                "kss_now": 5.2,
                "ear": 0.32,
                "mar": 0.28,
                "pitch": -4.0,
                "sustained_eye_closure_seconds": 0.0,
                "sustained_yawn_seconds": 0.0,
                "sustained_nod_seconds": 0.0,
                "raw_signals": {"avg_perclos": p, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
            })
            assert alert is None or alert["tier"] != "critical"

    def test_single_low_ear_frame_never_triggers_level_3(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # Single frame where EAR dips to 0.12 (sustained closure is only 0.1s)
        alert = mgr.evaluate({
            "timestamp": 100.0,
            "face_detected": True,
            "kss_now": 2.0,
            "ear": 0.12,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 0.1,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.04, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
        })
        assert alert is None

    def test_brief_eye_closures_under_1_5s_produce_no_alert(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # 0.5s closure
        alert_05 = mgr.evaluate({
            "timestamp": 100.0,
            "face_detected": True,
            "kss_now": 2.5,
            "ear": 0.12,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 0.5,
            "raw_signals": {"avg_perclos": 0.08, "microsleeps_in_window": 0},
        })
        assert alert_05 is None

        # 1.0s closure
        alert_10 = mgr.evaluate({
            "timestamp": 105.0,
            "face_detected": True,
            "kss_now": 3.0,
            "ear": 0.12,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 1.0,
            "raw_signals": {"avg_perclos": 0.10, "microsleeps_in_window": 0},
        })
        assert alert_10 is None

    def test_sustained_closure_escalates_properly(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # 1.6s closure -> Level 1 (Nudge)
        alert_16 = mgr.evaluate({
            "timestamp": 100.0,
            "face_detected": True,
            "kss_now": 5.5,
            "ear": 0.14,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 1.6,
            "raw_signals": {"avg_perclos": 0.15, "microsleeps_in_window": 0},
        })
        assert alert_16 is not None
        assert alert_16["tier"] == "nudge"

        # 2.0s closure -> Level 2 (Warning)
        mgr._last_alert_time["warning"] = 0.0
        alert_20 = mgr.evaluate({
            "timestamp": 120.0,
            "face_detected": True,
            "kss_now": 6.5,
            "ear": 0.14,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 2.0,
            "raw_signals": {"avg_perclos": 0.20, "microsleeps_in_window": 0},
        })
        assert alert_20 is not None
        assert alert_20["tier"] == "warning"

        # 2.6s closure -> Level 3 (Critical)
        mgr._last_alert_time["critical"] = 0.0
        alert_26 = mgr.evaluate({
            "timestamp": 140.0,
            "face_detected": True,
            "kss_now": 8.0,
            "ear": 0.14,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 2.6,
            "raw_signals": {"avg_perclos": 0.35, "microsleeps_in_window": 1},
        })
        assert alert_26 is not None
        assert alert_26["tier"] == "critical"
        assert "Prolonged eye closure" in alert_26["reason"]

    def test_multi_signal_convergence_triggers_level_3(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # Sustained closure (1.6s) SIMULTANEOUSLY with downward head nod (-18.0 deg)
        alert_multi = mgr.evaluate({
            "timestamp": 100.0,
            "face_detected": True,
            "kss_now": 7.5,
            "ear": 0.14,
            "mar": 0.28,
            "pitch": -18.0,
            "sustained_eye_closure_seconds": 1.6,
            "sustained_nod_seconds": 1.2,
            "raw_signals": {"avg_perclos": 0.25, "microsleeps_in_window": 1, "head_nods_in_window": 1},
        })
        assert alert_multi is not None
        assert alert_multi["tier"] == "critical"
        assert "Multi-signal fatigue" in alert_multi["reason"]

    def test_face_loss_resets_and_produces_no_alert(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # Face lost
        alert = mgr.evaluate({
            "timestamp": 100.0,
            "face_detected": False,
            "kss_now": 1.0,
            "ear": 0.0,
            "mar": 0.0,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.0, "microsleeps_in_window": 0},
        })
        assert alert is None

    def test_repeated_frames_in_critical_event_do_not_duplicate(self, tmp_path):
        log_file = tmp_path / "test_incidents.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # Frame 1: Critical triggers
        alert1 = mgr.evaluate({
            "timestamp": 100.0,
            "face_detected": True,
            "kss_now": 8.5,
            "ear": 0.12,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 2.7,
            "raw_signals": {"avg_perclos": 0.40, "microsleeps_in_window": 1},
        })
        assert alert1 is not None
        assert alert1["tier"] == "critical"

        # Frame 2: Next immediate frame (closure still 2.8s) -> MUST NOT duplicate
        alert2 = mgr.evaluate({
            "timestamp": 100.1,
            "face_detected": True,
            "kss_now": 8.5,
            "ear": 0.12,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 2.8,
            "raw_signals": {"avg_perclos": 0.40, "microsleeps_in_window": 1},
        })
        assert alert2 is None

        # Driver recovers (eyes open for >2.0s)
        mgr.evaluate({
            "timestamp": 105.0,
            "face_detected": True,
            "kss_now": 2.0,
            "ear": 0.30,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.10, "microsleeps_in_window": 0},
        })
        mgr.evaluate({
            "timestamp": 107.0,
            "face_detected": True,
            "kss_now": 2.0,
            "ear": 0.30,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.10, "microsleeps_in_window": 0},
        })

        # New critical event after cooldown -> fires as new distinct incident
        mgr._last_alert_time["critical"] = 100.0  # cooldown ok (now=120)
        alert_new = mgr.evaluate({
            "timestamp": 120.0,
            "face_detected": True,
            "kss_now": 8.5,
            "ear": 0.12,
            "mar": 0.28,
            "pitch": 0.0,
            "sustained_eye_closure_seconds": 2.6,
            "raw_signals": {"avg_perclos": 0.40, "microsleeps_in_window": 1},
        })
        assert alert_new is not None
        assert alert_new["tier"] == "critical"


class TestAlertStateTransitionsAndRecovery:
    def test_full_escalation_and_recovery_lifecycle(self, tmp_path):
        log_file = tmp_path / "test_lifecycle.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # 1. State: SAFE (Attentive Driver, EAR=0.30, MAR=0.25, KSS=1.5)
        safe_eval = mgr.evaluate({
            "timestamp": 10.0,
            "face_detected": True,
            "kss_now": 1.5,
            "ear": 0.30,
            "mar": 0.25,
            "pitch": -2.0,
            "sustained_eye_closure_seconds": 0.0,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.02, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
        })
        assert safe_eval is None

        # 2. State: Normal Blink (< 0.35s) -> Must remain SAFE
        blink_eval = mgr.evaluate({
            "timestamp": 10.3,
            "face_detected": True,
            "kss_now": 1.5,
            "ear": 0.12,
            "mar": 0.25,
            "pitch": -2.0,
            "sustained_eye_closure_seconds": 0.25,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.04, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
        })
        assert blink_eval is None

        # 3. State: Eyes close for 1.6s -> Escalation to LEVEL 1 (Nudge)
        mgr._last_alert_time["nudge"] = 0.0
        l1_eval = mgr.evaluate({
            "timestamp": 20.0,
            "face_detected": True,
            "kss_now": 5.5,
            "ear": 0.14,
            "mar": 0.25,
            "pitch": -2.0,
            "sustained_eye_closure_seconds": 1.6,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.18, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
        })
        assert l1_eval is not None
        assert l1_eval["tier"] == "nudge"

        # 4. State: Eyes close for 2.0s -> Escalation to LEVEL 2 (Warning)
        mgr._last_alert_time["warning"] = 0.0
        l2_eval = mgr.evaluate({
            "timestamp": 30.0,
            "face_detected": True,
            "kss_now": 6.8,
            "ear": 0.12,
            "mar": 0.25,
            "pitch": -5.0,
            "sustained_eye_closure_seconds": 2.0,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.24, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
        })
        assert l2_eval is not None
        assert l2_eval["tier"] == "warning"

        # 5. State: Eyes close for 2.6s + Microsleep -> Escalation to LEVEL 3 (Critical)
        mgr._last_alert_time["critical"] = 0.0
        l3_eval = mgr.evaluate({
            "timestamp": 40.0,
            "face_detected": True,
            "kss_now": 8.5,
            "ear": 0.10,
            "mar": 0.25,
            "pitch": -16.0,
            "sustained_eye_closure_seconds": 2.6,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 1.5,
            "raw_signals": {"avg_perclos": 0.45, "microsleeps_in_window": 1, "yawns_in_window": 0, "head_nods_in_window": 1},
        })
        assert l3_eval is not None
        assert l3_eval["tier"] == "critical"

        # 6. Recovery: Driver opens eyes, sits up, metrics normalize
        # Immediate next frame of recovery
        rec_eval_1 = mgr.evaluate({
            "timestamp": 45.0,
            "face_detected": True,
            "kss_now": 4.0,
            "ear": 0.32,
            "mar": 0.25,
            "pitch": -1.0,
            "sustained_eye_closure_seconds": 0.0,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.12, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
        })
        assert rec_eval_1 is None

        # Sustained recovery -> fully SAFE
        rec_eval_2 = mgr.evaluate({
            "timestamp": 50.0,
            "face_detected": True,
            "kss_now": 2.0,
            "ear": 0.32,
            "mar": 0.25,
            "pitch": -1.0,
            "sustained_eye_closure_seconds": 0.0,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.03, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 0},
        })
        assert rec_eval_2 is None

    def test_yawn_and_head_nod_alert_triggers(self, tmp_path):
        log_file = tmp_path / "test_yawn_nod.jsonl"
        mgr = AlertManager(log_path=str(log_file))

        # Sustained yawn alone (MAR > 0.55 for 1.6s) -> Level 1 Nudge
        mgr._last_alert_time["nudge"] = 0.0
        yawn_nudge = mgr.evaluate({
            "timestamp": 100.0,
            "face_detected": True,
            "kss_now": 5.2,
            "ear": 0.28,
            "mar": 0.65,
            "pitch": -2.0,
            "sustained_eye_closure_seconds": 0.0,
            "sustained_yawn_seconds": 1.6,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.05, "microsleeps_in_window": 0, "yawns_in_window": 1, "head_nods_in_window": 0},
        })
        assert yawn_nudge is not None
        assert yawn_nudge["tier"] == "nudge"
        assert "yawn" in yawn_nudge["reason"].lower()

        # Frequent yawns in window with elevated KSS (>=2 yawns, KSS >= 6.0) -> Level 2 Warning
        mgr._last_alert_time["warning"] = 0.0
        yawn_warn = mgr.evaluate({
            "timestamp": 110.0,
            "face_detected": True,
            "kss_now": 6.2,
            "ear": 0.28,
            "mar": 0.25,
            "pitch": -2.0,
            "sustained_eye_closure_seconds": 0.0,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 0.0,
            "raw_signals": {"avg_perclos": 0.05, "microsleeps_in_window": 0, "yawns_in_window": 2, "head_nods_in_window": 0},
        })
        assert yawn_warn is not None
        assert yawn_warn["tier"] == "warning"
        assert "yawning" in yawn_warn["reason"].lower()

        # Head nod alone (Pitch < -15 deg for 1.6s) -> Level 2 Warning
        mgr._last_alert_time["warning"] = 0.0
        nod_alert = mgr.evaluate({
            "timestamp": 120.0,
            "face_detected": True,
            "kss_now": 6.5,
            "ear": 0.28,
            "mar": 0.25,
            "pitch": -18.0,
            "sustained_eye_closure_seconds": 0.0,
            "sustained_yawn_seconds": 0.0,
            "sustained_nod_seconds": 1.6,
            "raw_signals": {"avg_perclos": 0.05, "microsleeps_in_window": 0, "yawns_in_window": 0, "head_nods_in_window": 1},
        })
        assert nod_alert is not None
        assert nod_alert["tier"] == "warning"
        assert "head nod" in nod_alert["reason"].lower()


# ===========================================================================
# NEW TESTS: Precise Alert Thresholds, Cooldown, Recovery & Multi-Signal
# ===========================================================================


def _awake_signals(timestamp):
    """A standard fully awake driver fusion result for baseline tests."""
    return {
        "timestamp": timestamp,
        "face_detected": True,
        "kss_now": 1.5,
        "ear": 0.30,
        "mar": 0.25,
        "pitch": -2.0,
        "sustained_eye_closure_seconds": 0.0,
        "sustained_yawn_seconds": 0.0,
        "sustained_nod_seconds": 0.0,
        "raw_signals": {
            "avg_perclos": 0.03,
            "microsleeps_in_window": 0,
            "yawns_in_window": 0,
            "head_nods_in_window": 0,
        },
    }


class TestAlertThresholdsPrecise:
    """Verify exact boundary conditions for each alert tier."""

    def test_safe_normal_open_eyes_no_alert(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        for t in [10.0, 10.1, 10.2]:
            assert mgr.evaluate(_awake_signals(t)) is None

    def test_natural_blink_under_1_5s_no_alert(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        for closure_s in [0.15, 0.25, 0.35, 0.8, 1.0, 1.4]:
            sig = {**_awake_signals(100.0 + closure_s), "ear": 0.12,
                   "sustained_eye_closure_seconds": closure_s,
                   "raw_signals": {"avg_perclos": 0.05, "microsleeps_in_window": 0,
                                   "yawns_in_window": 0, "head_nods_in_window": 0}}
            assert mgr.evaluate(sig) is None, f"{closure_s}s closure should not alert"

    def test_prolonged_closure_1_5s_triggers_nudge(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["nudge"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 5.0, "ear": 0.14,
                               "sustained_eye_closure_seconds": 1.5,
                               "raw_signals": {"avg_perclos": 0.10, "microsleeps_in_window": 0,
                                               "yawns_in_window": 0, "head_nods_in_window": 0}})
        assert alert is not None and alert["tier"] == "nudge"

    def test_yawn_1_5s_triggers_nudge(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["nudge"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 5.2, "ear": 0.28,
                               "mar": 0.65, "sustained_yawn_seconds": 1.5,
                               "raw_signals": {"avg_perclos": 0.05, "microsleeps_in_window": 0,
                                               "yawns_in_window": 1, "head_nods_in_window": 0}})
        assert alert is not None and alert["tier"] == "nudge"
        assert "yawn" in alert["reason"].lower()

    def test_perclos_15_pct_kss_5_triggers_nudge(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["nudge"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 5.1, "ear": 0.28,
                               "sustained_eye_closure_seconds": 0.0,
                               "raw_signals": {"avg_perclos": 0.15, "microsleeps_in_window": 0,
                                               "yawns_in_window": 0, "head_nods_in_window": 0}})
        assert alert is not None and alert["tier"] == "nudge"

    def test_closure_1_8s_triggers_warning(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["warning"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 6.2, "ear": 0.14,
                               "sustained_eye_closure_seconds": 1.8,
                               "raw_signals": {"avg_perclos": 0.18, "microsleeps_in_window": 0,
                                               "yawns_in_window": 0, "head_nods_in_window": 0}})
        assert alert is not None and alert["tier"] == "warning"

    def test_head_nod_1_5s_triggers_warning(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["warning"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 6.5, "pitch": -18.0,
                               "sustained_nod_seconds": 1.5,
                               "raw_signals": {"avg_perclos": 0.10, "microsleeps_in_window": 0,
                                               "yawns_in_window": 0, "head_nods_in_window": 1}})
        assert alert is not None and alert["tier"] == "warning"
        assert "head nod" in alert["reason"].lower()

    def test_two_yawns_kss_6_triggers_warning(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["warning"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 6.1, "ear": 0.28,
                               "sustained_eye_closure_seconds": 0.0,
                               "raw_signals": {"avg_perclos": 0.10, "microsleeps_in_window": 0,
                                               "yawns_in_window": 2, "head_nods_in_window": 0}})
        assert alert is not None and alert["tier"] == "warning"

    def test_closure_2_5s_triggers_critical(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["critical"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 7.5, "ear": 0.12,
                               "sustained_eye_closure_seconds": 2.5,
                               "raw_signals": {"avg_perclos": 0.30, "microsleeps_in_window": 0,
                                               "yawns_in_window": 0, "head_nods_in_window": 0}})
        assert alert is not None and alert["tier"] == "critical"
        assert "Prolonged eye closure" in alert["reason"]

    def test_multi_signal_closure_plus_head_nod_triggers_critical(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["critical"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 7.0, "ear": 0.14,
                               "pitch": -18.0, "sustained_eye_closure_seconds": 1.6,
                               "sustained_nod_seconds": 1.2,
                               "raw_signals": {"avg_perclos": 0.20, "microsleeps_in_window": 0,
                                               "yawns_in_window": 0, "head_nods_in_window": 1}})
        assert alert is not None and alert["tier"] == "critical"
        assert "Multi-signal" in alert["reason"]

    def test_multi_signal_closure_plus_yawn_triggers_critical(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["critical"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 7.2, "ear": 0.14,
                               "mar": 0.65, "pitch": -5.0,
                               "sustained_eye_closure_seconds": 1.6,
                               "sustained_yawn_seconds": 1.5,
                               "raw_signals": {"avg_perclos": 0.20, "microsleeps_in_window": 0,
                                               "yawns_in_window": 1, "head_nods_in_window": 0}})
        assert alert is not None and alert["tier"] == "critical"
        assert "Multi-signal" in alert["reason"]

    def test_repeated_microsleeps_high_perclos_triggers_critical(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["critical"] = 0.0
        alert = mgr.evaluate({**_awake_signals(100.0), "kss_now": 7.6, "ear": 0.18,
                               "sustained_eye_closure_seconds": 1.0,
                               "raw_signals": {"avg_perclos": 0.36, "microsleeps_in_window": 2,
                                               "yawns_in_window": 0, "head_nods_in_window": 0}})
        assert alert is not None and alert["tier"] == "critical"


class TestAlertCooldownAndDebounce:
    """Verify per-tier cooldown prevents audio/visual spam."""

    def test_nudge_within_cooldown_suppressed(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        payload = {**_awake_signals(100.0), "kss_now": 5.5, "ear": 0.14,
                   "sustained_eye_closure_seconds": 1.6,
                   "raw_signals": {"avg_perclos": 0.16, "microsleeps_in_window": 0,
                                   "yawns_in_window": 0, "head_nods_in_window": 0}}
        assert mgr.evaluate(payload) is not None
        payload["timestamp"] = 100.1
        assert mgr.evaluate(payload) is None, "Duplicate nudge within cooldown must be None"

    def test_warning_within_cooldown_suppressed(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        payload = {**_awake_signals(100.0), "kss_now": 6.5, "ear": 0.13,
                   "sustained_eye_closure_seconds": 2.0,
                   "raw_signals": {"avg_perclos": 0.22, "microsleeps_in_window": 0,
                                   "yawns_in_window": 0, "head_nods_in_window": 0}}
        assert mgr.evaluate(payload) is not None
        payload["timestamp"] = 100.5
        assert mgr.evaluate(payload) is None

    def test_critical_in_state_no_duplicate(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        payload = {**_awake_signals(100.0), "kss_now": 8.5, "ear": 0.12,
                   "sustained_eye_closure_seconds": 2.7,
                   "raw_signals": {"avg_perclos": 0.40, "microsleeps_in_window": 1,
                                   "yawns_in_window": 0, "head_nods_in_window": 0}}
        assert mgr.evaluate(payload)["tier"] == "critical"
        for dt in [0.1, 0.5, 1.0, 2.0]:
            payload["timestamp"] = 100.0 + dt
            assert mgr.evaluate(payload) is None, f"Frame at +{dt}s must be suppressed"

    def test_cooldown_expires_new_alert_fires(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["nudge"] = 0.0
        payload = {**_awake_signals(100.0), "kss_now": 5.5, "ear": 0.14,
                   "sustained_eye_closure_seconds": 1.6,
                   "raw_signals": {"avg_perclos": 0.16, "microsleeps_in_window": 0,
                                   "yawns_in_window": 0, "head_nods_in_window": 0}}
        assert mgr.evaluate(payload)["tier"] == "nudge"
        mgr._last_alert_time["nudge"] = 90.0  # 9s before t=99 -> cooldown ok
        payload["timestamp"] = 99.0
        alert2 = mgr.evaluate(payload)
        assert alert2 is not None and alert2["tier"] == "nudge"


class TestAlertRecoveryTransitions:
    """Verify recovery from each alert level back to SAFE."""

    def test_l1_to_safe_recovery(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["nudge"] = 0.0
        assert mgr.evaluate({**_awake_signals(100.0), "kss_now": 5.5, "ear": 0.14,
                              "sustained_eye_closure_seconds": 1.6,
                              "raw_signals": {"avg_perclos": 0.16, "microsleeps_in_window": 0,
                                              "yawns_in_window": 0, "head_nods_in_window": 0}})["tier"] == "nudge"
        for t in [102.0, 103.5, 105.0]:
            assert mgr.evaluate(_awake_signals(t)) is None

    def test_l2_to_safe_recovery(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["warning"] = 0.0
        assert mgr.evaluate({**_awake_signals(100.0), "kss_now": 6.8, "ear": 0.13,
                              "sustained_eye_closure_seconds": 2.0,
                              "raw_signals": {"avg_perclos": 0.22, "microsleeps_in_window": 0,
                                              "yawns_in_window": 0, "head_nods_in_window": 0}})["tier"] == "warning"
        for t in [103.0, 105.0, 110.0]:
            assert mgr.evaluate(_awake_signals(t)) is None

    def test_l3_to_safe_clears_in_critical_state(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "i.jsonl"))
        mgr._last_alert_time["critical"] = 0.0
        assert mgr.evaluate({**_awake_signals(100.0), "kss_now": 8.5, "ear": 0.12,
                              "sustained_eye_closure_seconds": 2.7,
                              "raw_signals": {"avg_perclos": 0.40, "microsleeps_in_window": 1,
                                              "yawns_in_window": 0, "head_nods_in_window": 0}})["tier"] == "critical"
        assert mgr._in_critical_state is True
        for t in [102.0, 104.0]:
            rec_payload = {**_awake_signals(t), "ear": 0.32, "sustained_eye_closure_seconds": 0.0,
                           "raw_signals": {"avg_perclos": 0.03, "microsleeps_in_window": 0,
                                           "yawns_in_window": 0, "head_nods_in_window": 0}}
            mgr.evaluate(rec_payload)
        assert mgr._in_critical_state is False

    def test_full_safe_l1_l2_l3_safe_lifecycle(self, tmp_path):
        mgr = AlertManager(log_path=str(tmp_path / "lifecycle.jsonl"))
        assert mgr.evaluate(_awake_signals(10.0)) is None
        mgr._last_alert_time["nudge"] = 0.0
        l1 = mgr.evaluate({**_awake_signals(20.0), "kss_now": 5.5, "ear": 0.14,
                            "sustained_eye_closure_seconds": 1.6,
                            "raw_signals": {"avg_perclos": 0.16, "microsleeps_in_window": 0,
                                            "yawns_in_window": 0, "head_nods_in_window": 0}})
        assert l1 is not None and l1["tier"] == "nudge"
        mgr._last_alert_time["warning"] = 0.0
        l2 = mgr.evaluate({**_awake_signals(30.0), "kss_now": 6.8, "ear": 0.13,
                            "sustained_eye_closure_seconds": 2.0,
                            "raw_signals": {"avg_perclos": 0.22, "microsleeps_in_window": 0,
                                            "yawns_in_window": 0, "head_nods_in_window": 0}})
        assert l2 is not None and l2["tier"] == "warning"
        mgr._last_alert_time["critical"] = 0.0
        l3 = mgr.evaluate({**_awake_signals(40.0), "kss_now": 8.5, "ear": 0.12,
                            "sustained_eye_closure_seconds": 2.7,
                            "raw_signals": {"avg_perclos": 0.40, "microsleeps_in_window": 1,
                                            "yawns_in_window": 0, "head_nods_in_window": 0}})
        assert l3 is not None and l3["tier"] == "critical"
        for t in [45.0, 47.0, 50.0]:
            assert mgr.evaluate({**_awake_signals(t), "ear": 0.32,
                                  "sustained_eye_closure_seconds": 0.0,
                                  "raw_signals": {"avg_perclos": 0.03, "microsleeps_in_window": 0,
                                                  "yawns_in_window": 0, "head_nods_in_window": 0}}) is None
        assert mgr._in_critical_state is False
