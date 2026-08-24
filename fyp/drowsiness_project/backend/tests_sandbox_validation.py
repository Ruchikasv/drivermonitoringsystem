"""
Sandbox validation script (NOT part of the shipped project's runtime).

This exercises every algorithm module with synthetic landmark/frame data so
the math and pipeline wiring can be verified in an environment without a
webcam or internet access to download the MediaPipe model file (both of
which are available on the user's actual laptop). It is intentionally kept
separate from the FaceLandmarker/webcam-dependent code path.
"""
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.ear_mar import compute_eye_mouth_metrics
from core.face_mesh import LEFT_EYE, RIGHT_EYE, MOUTH, HEAD_POSE_POINTS
from core.perclos import PerclosTracker
from core.head_pose import estimate_head_pose
from core.event_detectors import SustainedConditionDetector
from core.fusion_engine import FusionEngine
from core.alert_manager import AlertManager
from core.kss_mapper import rule_based_kss, kss_label, is_critical
from core import config


def make_synthetic_landmarks(eye_open=True, mouth_open=False, left_eye_open=None,
                              right_eye_open=None, n=468):
    """Builds a fake but geometrically plausible 468-point landmark array.
    left_eye_open/right_eye_open let a test simulate ONE eye occluded/closed
    while the other stays open (asymmetric case)."""
    pts = np.random.uniform(100, 500, size=(n, 2))

    l_open = eye_open if left_eye_open is None else left_eye_open
    r_open = eye_open if right_eye_open is None else right_eye_open

    ev_l = 8 if l_open else 0.5
    ev_r = 8 if r_open else 0.5

    left_eye_pts = np.array([
        [200, 220], [210, 220 - ev_l], [220, 220 - ev_l],
        [230, 220], [220, 220 + ev_l], [210, 220 + ev_l],
    ], dtype=float)
    for idx, p in zip(LEFT_EYE, left_eye_pts):
        pts[idx] = p

    right_eye_pts = np.array([
        [300, 220], [310, 220 - ev_r], [320, 220 - ev_r],
        [330, 220], [320, 220 + ev_r], [310, 220 + ev_r],
    ], dtype=float)
    for idx, p in zip(RIGHT_EYE, right_eye_pts):
        pts[idx] = p

    mv = 25 if mouth_open else 4
    mouth_pts = np.array([
        [220, 300], [300, 300], [250, 300 - mv], [255, 300 - mv // 2],
        [260, 300 + mv], [255, 300 + mv // 2], [240, 295], [240, 305],
    ], dtype=float)
    for idx, p in zip(MOUTH, mouth_pts):
        pts[idx] = p

    pts[HEAD_POSE_POINTS["nose_tip"]] = [260, 250]
    pts[HEAD_POSE_POINTS["chin"]] = [260, 340]
    pts[HEAD_POSE_POINTS["left_eye_corner"]] = [330, 220]
    pts[HEAD_POSE_POINTS["right_eye_corner"]] = [200, 220]
    pts[HEAD_POSE_POINTS["left_mouth_corner"]] = [300, 300]
    pts[HEAD_POSE_POINTS["right_mouth_corner"]] = [220, 300]

    return pts


def test_ear_mar():
    print("\n--- EAR / MAR ---")
    open_pts = make_synthetic_landmarks(eye_open=True, mouth_open=False)
    closed_pts = make_synthetic_landmarks(eye_open=False, mouth_open=False)
    yawn_pts = make_synthetic_landmarks(eye_open=True, mouth_open=True)

    ear_open = compute_eye_mouth_metrics(open_pts)["avg_ear"]
    ear_closed = compute_eye_mouth_metrics(closed_pts)["avg_ear"]
    mar_normal = compute_eye_mouth_metrics(open_pts)["mar"]
    mar_yawn = compute_eye_mouth_metrics(yawn_pts)["mar"]

    print(f"EAR open={ear_open:.3f}  EAR closed={ear_closed:.3f}")
    print(f"MAR normal={mar_normal:.3f}  MAR yawn={mar_yawn:.3f}")
    assert ear_open > ear_closed
    assert mar_yawn > mar_normal
    print("PASS")


def test_head_pose_frontal_reads_near_zero():
    print("\n--- Head pose (solvePnP + wraparound fix) ---")
    pts = make_synthetic_landmarks()
    pose = estimate_head_pose(pts, (480, 640, 3))
    print(pose)
    assert pose["valid"]
    # This is the regression test for the real-world bug: a front-facing
    # face was reading pitch ~ -177 degrees instead of ~0 due to a
    # decomposeProjectionMatrix wraparound quirk. After the fix it must be
    # within [-90, 90].
    assert -90 <= pose["pitch"] <= 90, f"pitch not wrapped correctly: {pose['pitch']}"
    print("PASS (pitch correctly wrapped into [-90, 90])")


def test_microsleep_requires_both_eyes_and_duration():
    print("\n--- Microsleep: both-eye requirement + duration (false-positive fix) ---")
    detector = SustainedConditionDetector(min_duration_seconds=0.8, cooldown_seconds=2.0)

    # Case 1: only ONE eye reads closed (e.g. occluded during a head turn)
    # for a long time -- must NOT trigger a microsleep.
    t = 0.0
    triggered_any = False
    for i in range(30):
        left_ear = 0.05   # closed / occluded
        right_ear = 0.30  # open
        both_closed = (left_ear < config.EAR_THRESHOLD) and (right_ear < config.EAR_THRESHOLD)
        t += 0.05
        if detector.update(both_closed, t):
            triggered_any = True
    print(f"One-eye-only closure (2s) triggered microsleep: {triggered_any}  (must be False)")
    assert not triggered_any, "single occluded eye should NOT trigger a microsleep"

    # Case 2: BOTH eyes closed for >= 0.8s -- must trigger exactly once.
    detector2 = SustainedConditionDetector(min_duration_seconds=0.8, cooldown_seconds=2.0)
    t = 0.0
    trigger_count = 0
    for i in range(30):
        both_closed = True
        t += 0.05
        if detector2.update(both_closed, t):
            trigger_count += 1
    print(f"Both-eyes-closed for 1.5s triggered microsleep {trigger_count} time(s) (must be exactly 1)")
    assert trigger_count == 1
    print("PASS")


def test_fusion_and_alerts():
    print("\n--- FusionEngine + AlertManager (no heart-rate signal) ---")
    engine = FusionEngine()
    alerts = AlertManager(log_path="/tmp/neuradrive_test_incidents.jsonl")
    if os.path.exists(alerts.log_path):
        os.remove(alerts.log_path)
    print(f"LSTM model loaded: {engine.model is not None}")

    now = time.time()
    fired_tiers = set()
    for step in range(40):
        severity = min(1.0, step / 30.0)
        engine.register_frame_events(
            perclos=0.05 + 0.35 * severity,
            blink_triggered=(step % 3 == 0),
            microsleep_triggered=(severity > 0.8 and step % 5 == 0),
            yawn_triggered=(severity > 0.4 and step % 4 == 0),
            head_nod_triggered=(severity > 0.6 and step % 6 == 0),
        )
        now += 5.1
        result = engine.maybe_aggregate(now=now)
        if result:
            alert = alerts.evaluate(result)
            if alert:
                fired_tiers.add(alert["tier"])
            if step % 10 == 0:
                print(f"  step={step} kss={result['kss_now']} "
                      f"label='{result['kss_label']}' source={result['score_source']} "
                      f"p_crit_soon={result['p_critical_soon']}")

    print(f"Alert tiers fired during escalation: {fired_tiers}")
    assert "critical" in fired_tiers or "warning" in fired_tiers
    print("PASS")

    # CSV-relevant check: confirm the incident log has no heart-rate field anywhere
    with open(alerts.log_path) as f:
        content = f.read()
    assert "hr" not in content.lower() and "heart" not in content.lower(), \
        "heart-rate should not appear anywhere in incident records"
    print("PASS (no heart-rate data anywhere in incident log)")


def test_kss_mapper():
    print("\n--- KSS mapper sanity (no hrv_proxy argument) ---")
    low = rule_based_kss(0.02, 15, 0, 0.2, 0)
    high = rule_based_kss(0.35, 30, 3, 2.5, 3)
    print(f"low fatigue KSS={low} ({kss_label(low)})  is_critical={is_critical(low)}")
    print(f"high fatigue KSS={high} ({kss_label(high)})  is_critical={is_critical(high)}")
    assert high > low
    assert is_critical(high)
    assert not is_critical(low)
    print("PASS")


if __name__ == "__main__":
    test_ear_mar()
    test_head_pose_frontal_reads_near_zero()
    test_microsleep_requires_both_eyes_and_duration()
    test_kss_mapper()
    test_fusion_and_alerts()
    print("\nALL SANDBOX VALIDATION TESTS PASSED")
