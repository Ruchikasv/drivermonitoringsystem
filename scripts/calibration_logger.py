"""
Standalone CNN + DMS Calibration Logger
=======================================

Records per-frame signals from the EXACT production pipeline (no modifications)
so you can evaluate whether the current +2.0 CNN KSS contribution is appropriate.

Usage:
    cd "driver monitoring"
    python -m scripts.calibration_logger

Controls (press while the OpenCV window is focused):
    1-8  : Start recording a numbered test scenario
    0    : Mark frames as "transition" (between scenarios)
    q    : Quit and print summary

Output:
    data/calibration/calibration_YYYYMMDD_HHMMSS.csv

IMPORTANT:
    - Does NOT modify any production code, thresholds, or model weights.
    - Alerts are evaluated but suppressed (logged, not actioned).
    - Uses the laptop webcam via OpenCV (not the IR camera path).
"""

import collections
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so app.* and training.* resolve
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import onnxruntime as ort

from app.drowsiness import config
from app.drowsiness.alert_manager import AlertManager
from app.drowsiness.ear_mar import compute_eye_mouth_metrics
from app.drowsiness.event_detectors import (
    HeadNodDetector,
    MicrosleepDetector,
    YawnDetector,
)
from app.drowsiness.face_mesh import FaceMeshDetector, LEFT_EYE, RIGHT_EYE, crop_eye
from app.drowsiness.head_pose import estimate_head_pose
from app.drowsiness.kss_mapper import rule_based_kss, kss_label
from app.drowsiness.perclos import PerclosTracker
from training.eye_cnn.preprocessing import preprocess_eye_image

# ---------------------------------------------------------------------------
# Test scenario labels
# ---------------------------------------------------------------------------
SCENARIO_LABELS = {
    "1": "Normal alert/open eyes",
    "2": "Normal blinking",
    "3": "Slowly partially close eyes",
    "4": "Sustained eye closure",
    "5": "Yawning",
    "6": "Head nod/downward movement",
    "7": "Normal talking/facial movement",
    "8": "Mixed normal behavior",
    "0": "Transition (unmarked)",
}

# Warm-up duration (seconds) after switching scenarios to let temporal
# trackers stabilise before recording data that counts toward the summary.
SCENARIO_WARMUP_SECONDS = 3.0

# CSV column order
CSV_COLUMNS = [
    # -- frame --
    "frame_num",
    "scenario",
    "scenario_label",
    "phase",           # 'warmup' or 'recording'
    # -- VISION --
    "timestamp",
    "ear",
    "mar",
    "perclos",
    "head_pitch",
    "head_yaw",
    "head_roll",
    "existing_kss",
    # -- CNN --
    "cnn_left_p_sleepy",
    "cnn_right_p_sleepy",
    "cnn_avg_p_sleepy",
    "cnn_smoothed_p_sleepy",
    "cnn_label",
    "cnn_latency_ms",
    # -- FUSION --
    "kss_before_cnn",
    "cnn_kss_contribution",
    "final_kss",
    "alert_level",
    # -- TIMING --
    "total_latency_ms",
]


def _cnn_contribution(p_sleepy: float) -> float:
    """Mirrors the CNN contribution formula in kss_mapper.rule_based_kss."""
    if p_sleepy > 0.7:
        return (p_sleepy - 0.7) * 2.0
    return 0.0


def main():
    # ------------------------------------------------------------------
    # 1. Output directory & CSV file
    # ------------------------------------------------------------------
    cal_dir = PROJECT_ROOT / "data" / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = cal_dir / f"calibration_{timestamp_str}.csv"

    # ------------------------------------------------------------------
    # 2. Initialise pipeline components (exact production versions)
    # ------------------------------------------------------------------
    print("[calibration] Initialising pipeline components...")

    face_mesh = FaceMeshDetector(max_faces=1)
    perclos_tracker = PerclosTracker()
    microsleep_det = MicrosleepDetector()
    yawn_det = YawnDetector()
    head_nod_det = HeadNodDetector()
    alert_mgr = AlertManager(log_path=str(cal_dir / f"calibration_alerts_{timestamp_str}.jsonl"))

    # CNN (ONNX)
    onnx_path = os.path.join("models", "eye_cnn", "eye_sleepiness.onnx")
    cnn_sess = None
    try:
        cnn_sess = ort.InferenceSession(str(PROJECT_ROOT / onnx_path))
        print(f"[calibration] CNN loaded from {onnx_path}")
    except Exception as e:
        print(f"[calibration] WARNING: CNN model not loaded ({e}). CNN columns will be 0.")

    cnn_history: collections.deque = collections.deque(maxlen=15)

    # ------------------------------------------------------------------
    # 3. Open webcam
    # ------------------------------------------------------------------
    cam_index = int(os.getenv("DMS_CAMERA_INDEX", "0"))
    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        print(f"[calibration] ERROR: Cannot open camera index {cam_index}")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print(f"[calibration] Camera opened (index {cam_index}).")

    # ------------------------------------------------------------------
    # 4. Main loop — record per-frame data
    # ------------------------------------------------------------------
    current_scenario = "0"
    frame_num = 0
    rows: list[dict] = []
    alert_state_changes = 0
    prev_alert_level = "none"
    scenario_start_time = time.time()   # track when current scenario began

    def _reset_temporal_state():
        """Reset calibration-session temporal trackers for a clean scenario start.
        Re-creates fresh instances of the same production classes — does NOT
        modify any production source code."""
        nonlocal perclos_tracker, microsleep_det, yawn_det, head_nod_det
        nonlocal alert_mgr, cnn_history, prev_alert_level
        perclos_tracker = PerclosTracker()
        microsleep_det = MicrosleepDetector()
        yawn_det = YawnDetector()
        head_nod_det = HeadNodDetector()
        alert_mgr = AlertManager(log_path=str(cal_dir / f"calibration_alerts_{timestamp_str}.jsonl"))
        cnn_history.clear()
        prev_alert_level = "none"

    print()
    print("=" * 68)
    print("  CNN + DMS CALIBRATION LOGGER")
    print("=" * 68)
    print("  Press 1-8 to start a test scenario")
    print("  Press 0   to mark transition frames")
    print("  Press Q   to finish and print summary")
    print("=" * 68)
    print()

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                print("[calibration] Camera read failed. Exiting.")
                break

            frame_start = time.time()
            now = frame_start
            frame_num += 1

            # -- 4a. Face Mesh ------------------------------------------------
            landmarks_px, landmarks_norm = face_mesh.process(frame_bgr)
            face_detected = landmarks_px is not None

            # Determine warm-up vs recording phase for current scenario
            elapsed_in_scenario = now - scenario_start_time
            is_warmup = elapsed_in_scenario < SCENARIO_WARMUP_SECONDS
            phase = "warmup" if is_warmup else "recording"

            if not face_detected:
                # Still record the frame with zero signals
                row = {c: 0 for c in CSV_COLUMNS}
                row["frame_num"] = frame_num
                row["scenario"] = current_scenario
                row["scenario_label"] = SCENARIO_LABELS.get(current_scenario, "?")
                row["phase"] = phase
                row["timestamp"] = round(now, 4)
                row["existing_kss"] = 1.0
                row["kss_before_cnn"] = 1.0
                row["final_kss"] = 1.0
                row["cnn_label"] = "NO_FACE"
                row["alert_level"] = "none"
                row["total_latency_ms"] = round((time.time() - frame_start) * 1000, 2)
                writer.writerow(row)
                rows.append(row)

                # Draw no-face overlay
                phase_text = "WARMING UP" if is_warmup else "RECORDING"
                phase_color = (0, 165, 255) if is_warmup else (0, 255, 0)
                cv2.putText(frame_bgr, "NO FACE DETECTED", (15, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.putText(frame_bgr, f"Scenario {current_scenario}: {SCENARIO_LABELS.get(current_scenario, '?')} [{phase_text}]",
                            (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, phase_color, 1)
                cv2.imshow("Calibration Logger", frame_bgr)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if chr(key) in SCENARIO_LABELS:
                    old = current_scenario
                    current_scenario = chr(key)
                    if old != current_scenario:
                        _reset_temporal_state()
                        scenario_start_time = now
                        print(f"  → Scenario changed: {current_scenario} — {SCENARIO_LABELS[current_scenario]} (state reset, {SCENARIO_WARMUP_SECONDS:.0f}s warm-up)")
                continue

            # -- 4b. EAR, MAR -------------------------------------------------
            em = compute_eye_mouth_metrics(landmarks_px)
            ear = em["avg_ear"]
            mar = em["mar"]

            # -- 4c. PERCLOS ---------------------------------------------------
            perclos_res = perclos_tracker.update(ear, timestamp=now, face_detected=True)
            perclos = perclos_res["perclos"]
            blink_trig = perclos_res["blink_triggered"]
            blink_rate = perclos_res["blink_rate_per_min"]

            # -- 4d. Head Pose -------------------------------------------------
            hp = estimate_head_pose(landmarks_px, frame_bgr.shape)
            pitch = hp["pitch"] if hp["valid"] else 0.0
            yaw   = hp["yaw"]   if hp["valid"] else 0.0
            roll  = hp["roll"]  if hp["valid"] else 0.0

            # -- 4e. Event Detectors ------------------------------------------
            microsleep_trig = microsleep_det.update(ear, now, face_detected=True)
            yawn_trig       = yawn_det.update(mar, now, face_detected=True)
            head_nod_trig   = head_nod_det.update(pitch, now, face_detected=True)

            sustained_closure_s = microsleep_det.get_sustained_duration(now) if ear < config.EAR_THRESHOLD else 0.0
            sustained_yawn_s    = yawn_det.get_sustained_duration(now) if mar > config.MAR_THRESHOLD else 0.0
            sustained_nod_s     = head_nod_det.get_sustained_duration(now) if pitch < config.HEAD_NOD_PITCH_THRESHOLD_DEG else 0.0

            microsleeps_recent = microsleep_det.get_recent_count(now, 60.0)
            yawns_recent       = yawn_det.get_recent_count(now, 60.0)
            head_nods_recent   = head_nod_det.get_recent_count(now, 60.0)

            # -- 4f. CNN Inference (exact production logic) --------------------
            cnn_start = time.time()
            cnn_left_p = 0.0
            cnn_right_p = 0.0
            cnn_avg_p = 0.0
            cnn_smoothed_p = 0.0

            if cnn_sess is not None:
                try:
                    # Left eye
                    left_crop, _ = crop_eye(frame_bgr, landmarks_px, LEFT_EYE)
                    if left_crop.size > 0:
                        tensor_l = preprocess_eye_image(left_crop).numpy()
                        logits_l = cnn_sess.run(None, {"eye_image": tensor_l})[0]
                        exp_l = np.exp(logits_l - logits_l.max())
                        probs_l = (exp_l / exp_l.sum()).squeeze()
                        cnn_left_p = float(probs_l[1])

                    # Right eye
                    right_crop, _ = crop_eye(frame_bgr, landmarks_px, RIGHT_EYE)
                    if right_crop.size > 0:
                        tensor_r = preprocess_eye_image(right_crop).numpy()
                        logits_r = cnn_sess.run(None, {"eye_image": tensor_r})[0]
                        exp_r = np.exp(logits_r - logits_r.max())
                        probs_r = (exp_r / exp_r.sum()).squeeze()
                        cnn_right_p = float(probs_r[1])

                    cnn_avg_p = (cnn_left_p + cnn_right_p) / 2.0
                    cnn_history.append(cnn_avg_p)
                    cnn_smoothed_p = sum(cnn_history) / len(cnn_history)
                except Exception as e:
                    pass  # silently skip bad frames just like production

            cnn_latency_ms = (time.time() - cnn_start) * 1000.0
            cnn_label = "SLEEPY" if cnn_smoothed_p > 0.5 else "AWAKE"

            # -- 4g. KSS computation (decomposed for logging) -----------------
            # KSS WITHOUT the CNN contribution
            kss_before_cnn = rule_based_kss(
                perclos=perclos,
                blink_rate_per_min=blink_rate,
                microsleep_count_recent=microsleeps_recent,
                yawn_rate_per_min=float(yawns_recent),
                head_nod_events_recent=head_nods_recent,
                sustained_eye_closure_seconds=sustained_closure_s,
                cnn_p_sleepy=0.0,  # explicitly zero to isolate
            )

            # CNN KSS contribution (mirrors kss_mapper line 82-83)
            cnn_kss_contrib = _cnn_contribution(cnn_smoothed_p)

            # Final KSS WITH the CNN contribution (exact production call)
            final_kss = rule_based_kss(
                perclos=perclos,
                blink_rate_per_min=blink_rate,
                microsleep_count_recent=microsleeps_recent,
                yawn_rate_per_min=float(yawns_recent),
                head_nod_events_recent=head_nods_recent,
                sustained_eye_closure_seconds=sustained_closure_s,
                cnn_p_sleepy=cnn_smoothed_p,
            )

            # -- 4h. Alert Evaluation (suppressed — log only) -----------------
            fusion_result = {
                "timestamp": now,
                "face_detected": True,
                "kss_now": final_kss,
                "kss_label": kss_label(final_kss),
                "is_critical": final_kss >= config.KSS_CRITICAL_THRESHOLD,
                "p_critical_soon": None,
                "score_source": "rule_based_instant",
                "ear": round(ear, 3),
                "mar": round(mar, 3),
                "pitch": round(pitch, 1),
                "sustained_eye_closure_seconds": round(sustained_closure_s, 2),
                "sustained_yawn_seconds": round(sustained_yawn_s, 2),
                "sustained_nod_seconds": round(sustained_nod_s, 2),
                "raw_signals": {
                    "avg_perclos": round(perclos, 3),
                    "blink_rate_per_min": blink_rate,
                    "microsleeps_in_window": microsleeps_recent,
                    "yawns_in_window": yawns_recent,
                    "head_nods_in_window": head_nods_recent,
                },
            }
            alert = alert_mgr.evaluate(fusion_result)
            current_alert_level = alert["tier"] if alert else "none"

            if current_alert_level != prev_alert_level:
                alert_state_changes += 1
                prev_alert_level = current_alert_level

            total_latency_ms = (time.time() - frame_start) * 1000.0

            # -- 4i. Write CSV row -------------------------------------------
            row = {
                "frame_num": frame_num,
                "scenario": current_scenario,
                "scenario_label": SCENARIO_LABELS.get(current_scenario, "?"),
                "phase": phase,
                "timestamp": round(now, 4),
                "ear": round(ear, 4),
                "mar": round(mar, 4),
                "perclos": round(perclos, 4),
                "head_pitch": round(pitch, 1),
                "head_yaw": round(yaw, 1),
                "head_roll": round(roll, 1),
                "existing_kss": round(final_kss, 2),
                "cnn_left_p_sleepy": round(cnn_left_p, 4),
                "cnn_right_p_sleepy": round(cnn_right_p, 4),
                "cnn_avg_p_sleepy": round(cnn_avg_p, 4),
                "cnn_smoothed_p_sleepy": round(cnn_smoothed_p, 4),
                "cnn_label": cnn_label,
                "cnn_latency_ms": round(cnn_latency_ms, 2),
                "kss_before_cnn": round(kss_before_cnn, 2),
                "cnn_kss_contribution": round(cnn_kss_contrib, 4),
                "final_kss": round(final_kss, 2),
                "alert_level": current_alert_level,
                "total_latency_ms": round(total_latency_ms, 2),
            }
            writer.writerow(row)
            rows.append(row)

            # -- 4j. Live overlay on frame -----------------------------------
            annotated = frame_bgr.copy()
            color_map = {
                "none": (0, 255, 0),
                "nudge": (0, 255, 255),
                "warning": (0, 165, 255),
                "critical": (0, 0, 255),
            }
            overlay_color = color_map.get(current_alert_level, (255, 255, 255))

            # Phase indicator (warm-up vs recording)
            if is_warmup:
                phase_text = f"WARMING UP ({SCENARIO_WARMUP_SECONDS - elapsed_in_scenario:.1f}s)"
                phase_color = (0, 165, 255)  # orange
            else:
                phase_text = "RECORDING"
                phase_color = (0, 255, 0)    # green

            cv2.putText(annotated,
                        f"Scenario {current_scenario}: {SCENARIO_LABELS.get(current_scenario, '?')}",
                        (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 1, cv2.LINE_AA)
            cv2.putText(annotated,
                        phase_text,
                        (15, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.55, phase_color, 2, cv2.LINE_AA)
            cv2.putText(annotated,
                        f"EAR: {ear:.3f}  MAR: {mar:.3f}  PERCLOS: {perclos*100:.1f}%",
                        (15, 71), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 200), 1, cv2.LINE_AA)
            cv2.putText(annotated,
                        f"Pitch: {pitch:.1f}  KSS: {final_kss:.1f}  Alert: {current_alert_level.upper()}",
                        (15, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.48, overlay_color, 1, cv2.LINE_AA)
            cv2.putText(annotated,
                        f"CNN P(S): L={cnn_left_p:.3f} R={cnn_right_p:.3f} Avg={cnn_avg_p:.3f} Sm={cnn_smoothed_p:.3f} [{cnn_label}]",
                        (15, 117), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 255), 1, cv2.LINE_AA)
            cv2.putText(annotated,
                        f"KSS(no CNN): {kss_before_cnn:.1f}  CNN contrib: +{cnn_kss_contrib:.2f}  Final: {final_kss:.1f}",
                        (15, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 255, 180), 1, cv2.LINE_AA)
            cv2.putText(annotated,
                        f"Frame {frame_num}  |  CNN: {cnn_latency_ms:.0f}ms  Total: {total_latency_ms:.0f}ms",
                        (15, 163), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1, cv2.LINE_AA)

            cv2.imshow("Calibration Logger", annotated)

            # -- 4k. Keyboard input ------------------------------------------
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            key_char = chr(key) if key < 128 else ""
            if key_char in SCENARIO_LABELS:
                old = current_scenario
                current_scenario = key_char
                if old != current_scenario:
                    _reset_temporal_state()
                    scenario_start_time = now
                    print(f"  → Scenario changed: {current_scenario} — {SCENARIO_LABELS[current_scenario]} (state reset, {SCENARIO_WARMUP_SECONDS:.0f}s warm-up)")

    # ------------------------------------------------------------------
    # 5. Cleanup
    # ------------------------------------------------------------------
    cap.release()
    cv2.destroyAllWindows()
    face_mesh.close()

    print()
    print(f"[calibration] {frame_num} frames recorded → {csv_path}")
    print()

    # ------------------------------------------------------------------
    # 6. Per-scenario summary
    # ------------------------------------------------------------------
    _print_summary(rows)


def _print_summary(rows: list[dict]):
    """Print a per-scenario summary table.
    Only 'recording' phase frames are used for summary statistics;
    'warmup' frames are excluded so each scenario is independently measured."""
    from collections import defaultdict

    # Separate recording vs warmup
    recording_rows = [r for r in rows if r.get("phase") == "recording"]
    warmup_rows = [r for r in rows if r.get("phase") == "warmup"]

    scenarios = defaultdict(list)
    for r in recording_rows:
        scenarios[r["scenario"]].append(r)

    # Also count warmup frames per scenario for info
    warmup_by_scenario = defaultdict(int)
    for r in warmup_rows:
        warmup_by_scenario[r["scenario"]] += 1

    # Table header
    hdr = (
        f"{'Scenario':<6} {'Label':<32} "
        f"{'avgP(S)':>7} {'maxP(S)':>7} "
        f"{'avgEAR':>7} {'minEAR':>7} "
        f"{'PERCLOS':>8} "
        f"{'KSS-CNN':>8} {'CNN+':>6} {'FinalKSS':>8} "
        f"{'AlertΔ':>6} "
        f"{'CNNms':>6} {'Totalms':>8} "
        f"{'Rec':>5} {'Warm':>5}"
    )
    print("=" * len(hdr))
    print("  PER-SCENARIO CALIBRATION SUMMARY  (warm-up frames excluded)")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))

    for scenario_key in sorted(scenarios.keys()):
        srows = scenarios[scenario_key]
        n = len(srows)
        if n == 0:
            continue

        label = SCENARIO_LABELS.get(scenario_key, "?")
        n_warmup = warmup_by_scenario.get(scenario_key, 0)

        # CNN P(SLEEPY) — use smoothed
        p_vals = [float(r["cnn_smoothed_p_sleepy"]) for r in srows]
        avg_p = sum(p_vals) / n
        max_p = max(p_vals)

        # EAR
        ear_vals = [float(r["ear"]) for r in srows]
        avg_ear = sum(ear_vals) / n
        min_ear = min(ear_vals)

        # PERCLOS
        perclos_vals = [float(r["perclos"]) for r in srows]
        avg_perclos = sum(perclos_vals) / n

        # KSS before CNN
        kss_no_cnn_vals = [float(r["kss_before_cnn"]) for r in srows]
        avg_kss_no_cnn = sum(kss_no_cnn_vals) / n

        # CNN contribution
        cnn_contrib_vals = [float(r["cnn_kss_contribution"]) for r in srows]
        avg_cnn_contrib = sum(cnn_contrib_vals) / n

        # Final KSS
        final_kss_vals = [float(r["final_kss"]) for r in srows]
        avg_final_kss = sum(final_kss_vals) / n

        # Alert state changes within this scenario
        alert_changes = 0
        prev = None
        for r in srows:
            al = r["alert_level"]
            if prev is not None and al != prev:
                alert_changes += 1
            prev = al

        # Latency
        cnn_lat = [float(r["cnn_latency_ms"]) for r in srows]
        avg_cnn_lat = sum(cnn_lat) / n

        total_lat = [float(r["total_latency_ms"]) for r in srows]
        avg_total_lat = sum(total_lat) / n

        print(
            f"{scenario_key:<6} {label:<32} "
            f"{avg_p:>7.4f} {max_p:>7.4f} "
            f"{avg_ear:>7.4f} {min_ear:>7.4f} "
            f"{avg_perclos*100:>7.2f}% "
            f"{avg_kss_no_cnn:>8.2f} {avg_cnn_contrib:>+5.2f} {avg_final_kss:>8.2f} "
            f"{alert_changes:>6} "
            f"{avg_cnn_lat:>6.1f} {avg_total_lat:>8.1f} "
            f"{n:>5} {n_warmup:>5}"
        )

    print()
    # Key calibration metrics (recording frames only)
    if recording_rows:
        overall_avg_contrib = sum(float(r["cnn_kss_contribution"]) for r in recording_rows) / len(recording_rows)
        overall_max_contrib = max(float(r["cnn_kss_contribution"]) for r in recording_rows)
        alert_frames = [r for r in recording_rows if r["scenario"] == "1"]
        alert_avg_p = (sum(float(r["cnn_smoothed_p_sleepy"]) for r in alert_frames) / len(alert_frames)) if alert_frames else 0
        sleepy_frames = [r for r in recording_rows if r["scenario"] == "4"]
        sleepy_avg_p = (sum(float(r["cnn_smoothed_p_sleepy"]) for r in sleepy_frames) / len(sleepy_frames)) if sleepy_frames else 0

        print("KEY CALIBRATION METRICS (recording frames only):")
        print(f"  Total recording frames            : {len(recording_rows)}")
        print(f"  Total warm-up frames (excluded)    : {len(warmup_rows)}")
        print(f"  Overall avg CNN KSS contribution  : {overall_avg_contrib:+.4f}")
        print(f"  Overall max CNN KSS contribution  : {overall_max_contrib:+.4f}")
        if alert_frames:
            print(f"  Scenario 1 (alert) avg P(SLEEPY)  : {alert_avg_p:.4f}")
        if sleepy_frames:
            print(f"  Scenario 4 (closure) avg P(SLEEPY): {sleepy_avg_p:.4f}")
        print()
        print("  VERDICT: Review CSV and the above table to determine whether")
        print("  the current +2.0 max CNN KSS contribution is appropriate.")
        print()


if __name__ == "__main__":
    main()
