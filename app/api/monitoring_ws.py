"""
WebSocket endpoint for real-time driver drowsiness monitoring.

Endpoint:
  WS /ws/monitor/{session_id}

Provides:
- 15 FPS real-time MediaPipe face mesh processing
- EAR, MAR, PERCLOS, head-pose estimation
- Temporal multi-modal fusion via FatigueLSTM / rule-based KSS
- Automatic styled composite evidence screenshot generation on alerts
- Real-time event logging to SQLite
- Live metrics cache for Owner Portal metrics polling
"""

import asyncio
import base64
import collections
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import onnxruntime as ort
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.vehicle_repository import VehicleRepository
from app.drowsiness import config
from app.drowsiness.alert_manager import AlertManager
from app.drowsiness.ear_mar import compute_eye_mouth_metrics
from app.drowsiness.event_detectors import (
    HeadNodDetector,
    MicrosleepDetector,
    YawnDetector,
)
from app.drowsiness.evidence import generate_evidence_screenshot
from app.drowsiness.face_mesh import FaceMeshDetector, LEFT_EYE, RIGHT_EYE, crop_eye
from app.drowsiness.fusion_engine import FusionEngine
from app.drowsiness.head_pose import estimate_head_pose
from app.drowsiness.perclos import PerclosTracker
from training.eye_cnn.preprocessing import preprocess_eye_image

from app.distraction.phone_detector import PhoneDetector
from app.distraction.distraction_detector import PhoneDistractionDetector
from app.distraction.audio import trigger_distraction_beep
from app.distraction.gaze import estimate_gaze_ratios


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Monitoring WebSocket"])

# In-memory real-time metrics cache for Owner Portal polling (metrics-only)
LIVE_SESSION_METRICS: dict[int, dict] = {}
# In-memory most recent raw camera frame per active session for evidence capture
LIVE_SESSION_FRAMES: dict[int, np.ndarray] = {}


def get_live_session_frame(session_id: int) -> Optional[np.ndarray]:
    """Retrieve the most recent clean camera frame captured for a live monitoring session."""
    frame = LIVE_SESSION_FRAMES.get(session_id)
    return frame.copy() if frame is not None else None


def get_any_active_frame() -> Optional[np.ndarray]:
    """Retrieve the most recent camera frame from any currently active live session."""
    for frame in list(LIVE_SESSION_FRAMES.values()):
        if frame is not None and getattr(frame, "size", 0) > 0:
            return frame.copy()
    return None


def get_live_metrics(session_id: int) -> Optional[dict]:
    """Retrieve the latest real-time metrics snapshot for a session."""
    data = LIVE_SESSION_METRICS.get(session_id)
    if not data:
        return None
    from app.hardware.alcohol_sensor import mq3_serial_reader
    is_locked = mq3_serial_reader.is_locked()
    item = data.copy()
    item["is_locked"] = is_locked
    if is_locked:
        item["status"] = "PAUSED"
        item["is_paused"] = True
        if "metrics" in item and isinstance(item["metrics"], dict):
            item["metrics"]["risk_level"] = "RESTRICTED"
        if "fusion" in item and isinstance(item["fusion"], dict):
            item["fusion"]["kss_label"] = "Operation Restricted"
    return item


def get_all_live_metrics(owner_id: Optional[int] = None) -> dict[int, dict]:
    """Retrieve active session metrics snapshots, optionally scoped by owner and alcohol lockout."""
    from app.hardware.alcohol_sensor import mq3_serial_reader
    is_locked = mq3_serial_reader.is_locked()
    res = {}
    for sid, data in LIVE_SESSION_METRICS.items():
        if owner_id is not None and data.get("owner_id") != owner_id:
            continue
        item = data.copy()
        item["is_locked"] = is_locked
        if is_locked:
            item["status"] = "PAUSED"
            item["is_paused"] = True
            if "metrics" in item and isinstance(item["metrics"], dict):
                item["metrics"]["risk_level"] = "RESTRICTED"
            if "fusion" in item and isinstance(item["fusion"], dict):
                item["fusion"]["kss_label"] = "Operation Restricted"
        res[sid] = item
    return res


def update_live_session_pause_state(session_id: int, is_paused: bool):
    """Update in-memory live metrics cache to reflect pause/resume state."""
    if session_id in LIVE_SESSION_METRICS:
        LIVE_SESSION_METRICS[session_id]["is_paused"] = is_paused
        LIVE_SESSION_METRICS[session_id]["status"] = "PAUSED" if is_paused else "ACTIVE"
        if is_paused:
            LIVE_SESSION_METRICS[session_id]["latest_alert"] = None
            if "metrics" in LIVE_SESSION_METRICS[session_id]:
                LIVE_SESSION_METRICS[session_id]["metrics"]["risk_level"] = "PAUSED"
                LIVE_SESSION_METRICS[session_id]["metrics"]["microsleep_active"] = False
                LIVE_SESSION_METRICS[session_id]["metrics"]["yawn_active"] = False
                LIVE_SESSION_METRICS[session_id]["metrics"]["head_nod_active"] = False
                LIVE_SESSION_METRICS[session_id]["metrics"]["phone_detected"] = False
                LIVE_SESSION_METRICS[session_id]["metrics"]["distraction_active"] = False
                LIVE_SESSION_METRICS[session_id]["metrics"]["distraction_confirmed"] = False
                LIVE_SESSION_METRICS[session_id]["metrics"]["distraction_duration"] = 0.0


class DriverSessionProcessor:
    """Encapsulates the complete drowsiness detection pipeline for one driver session."""

    def __init__(
        self,
        session_id: int,
        driver_id: int,
        driver_name: str,
        vehicle_reg: Optional[str],
        phone_detector: Optional[Any] = None,
        distraction_detector: Optional[Any] = None,
    ):
        self.session_id = session_id
        self.driver_id = driver_id
        self.driver_name = driver_name
        self.vehicle_reg = vehicle_reg

        # Pipeline components
        self.face_mesh = FaceMeshDetector(max_faces=1)
        self.perclos_tracker = PerclosTracker()
        self.microsleep_detector = MicrosleepDetector()
        self.yawn_detector = YawnDetector()
        self.head_nod_detector = HeadNodDetector()
        self.fusion_engine = FusionEngine()
        self.alert_manager = AlertManager()

        # Phone Distraction Detection components
        self.phone_detector = phone_detector if phone_detector is not None else PhoneDetector(lazy_load=True)
        self.distraction_detector = distraction_detector if distraction_detector is not None else PhoneDistractionDetector()
        self._frame_count = 0
        self._last_phone_detections: list[dict] = []
        self._last_all_detections: list[dict] = []
        
        # CNN Integration
        onnx_path = os.path.join("models", "eye_cnn", "eye_sleepiness.onnx")
        try:
            self.cnn_sess = ort.InferenceSession(onnx_path)
            logger.info("Loaded CNN InferenceSession from %s", onnx_path)
        except Exception as e:
            logger.error("Failed to load CNN model from %s: %s", onnx_path, e)
            self.cnn_sess = None
            
        self.cnn_history = collections.deque(maxlen=15)

    def reset_all_detectors(self):
        """Reset all sustained condition detectors and alert states to prevent stale alerts on resume."""
        self.microsleep_detector.reset_condition()
        self.yawn_detector.reset_condition()
        self.head_nod_detector.reset_condition()
        self.distraction_detector.reset()
        self._last_phone_detections = []
        self._last_all_detections = []
        self._frame_count = 0
        self.perclos_tracker = PerclosTracker()
        self.fusion_engine = FusionEngine()
        self.alert_manager = AlertManager()

    def process_frame(self, frame_bgr: np.ndarray, now: float = None, extra_sensors: dict = None, debug_mode: bool = False) -> tuple[np.ndarray, dict, Optional[dict]]:
        """
        Process a single BGR camera frame through the entire drowsiness pipeline.
        Returns:
            annotated_frame (np.ndarray): Frame with visual debug overlays
            metrics (dict): Real-time metrics (EAR, MAR, PERCLOS, head pose, KSS, etc.)
            alert (dict or None): Triggered alert payload if an alert threshold was crossed
        """
        frame_start_time = time.time()
        now = now or frame_start_time
        extra_sensors = extra_sensors or {}
        annotated = frame_bgr.copy()
        h, w = annotated.shape[:2]

        # 1. Face Mesh
        landmarks_px, landmarks_norm = self.face_mesh.process(frame_bgr)
        face_detected = landmarks_px is not None

        if not face_detected:
            self.microsleep_detector.reset_condition()
            self.yawn_detector.reset_condition()
            self.head_nod_detector.reset_condition()
            self.distraction_detector.reset_active_glance()
            self._last_phone_detections = []

            # Default zero-signal metrics on face loss
            metrics = {
                "face_detected": False,
                "ear": 0.0,
                "mar": 0.0,
                "perclos": round(self.perclos_tracker.current_perclos(), 3),
                "pitch": 0.0,
                "head_pitch": 0.0,
                "yaw": 0.0,
                "head_yaw": 0.0,
                "roll": 0.0,
                "head_roll": 0.0,
                "kss": 1.0,
                "risk_score": 0.0,
                "risk_level": "NO_FACE",
                "confidence": 0.0,
                "contributing_factors": ["Face tracking unavailable"],
                "microsleep_active": False,
                "yawn_active": False,
                "head_nod_active": False,
                "critical_active": False,
                "phone_detected": False,
                "phone_confidence": 0.0,
                "phone_box": None,
                "distraction_active": False,
                "distraction_confirmed": False,
                "distraction_duration": 0.0,
                "distraction_triggered": False,
                "distraction_type": "phone",
                "distraction": {
                    "distraction_active": False,
                    "distraction_confirmed": False,
                    "triggered": False,
                    "duration_seconds": 0.0,
                    "cooldown_active": False,
                    "looking_down": False,
                    "phone_present": False,
                    "distraction_type": "phone",
                },
                "distraction_alert": None,
                "fusion": {
                    "timestamp": now,
                    "kss_now": 1.0,
                    "kss_label": "Face not detected",
                    "is_critical": False,
                    "p_critical_soon": None,
                    "score_source": "face_lost",
                    "raw_signals": {
                        "avg_perclos": 0.0,
                        "blink_rate_per_min": 0.0,
                        "microsleeps_in_window": 0,
                        "yawns_in_window": 0,
                        "head_nods_in_window": 0,
                    },
                },
            }
            return annotated, metrics, None

        # 2. Geometric Metrics: EAR & MAR
        ear_metrics = compute_eye_mouth_metrics(landmarks_px)
        ear = ear_metrics["avg_ear"]
        mar = ear_metrics["mar"]

        # 3. PERCLOS Tracker
        perclos_result = self.perclos_tracker.update(ear, timestamp=now, face_detected=True)
        perclos = perclos_result["perclos"]
        blink_trig = perclos_result["blink_triggered"]
        blink_rate = perclos_result["blink_rate_per_min"]

        # 4. 3D Head Pose & Eye Gaze Estimation
        head_pose = estimate_head_pose(landmarks_px, frame_bgr.shape)
        pitch = head_pose["pitch"] if head_pose["valid"] else 0.0
        yaw = head_pose["yaw"] if head_pose["valid"] else 0.0
        roll = head_pose["roll"] if head_pose["valid"] else 0.0
        gaze_info = estimate_gaze_ratios(landmarks_px)

        # 5. Sustained Condition Detectors (time-based)
        microsleep_trig = self.microsleep_detector.update(ear, now, face_detected=True)
        yawn_trig = self.yawn_detector.update(mar, now, face_detected=True)
        head_nod_trig = self.head_nod_detector.update(pitch, now, face_detected=True)

        # Durations and rolling window counts
        sustained_closure_s = self.microsleep_detector.get_sustained_duration(now) if ear < config.EAR_THRESHOLD else 0.0
        sustained_yawn_s = self.yawn_detector.get_sustained_duration(now) if mar > config.MAR_THRESHOLD else 0.0
        sustained_nod_s = self.head_nod_detector.get_sustained_duration(now) if pitch < config.HEAD_NOD_PITCH_THRESHOLD_DEG else 0.0

        microsleeps_recent = self.microsleep_detector.get_recent_count(now, window_seconds=60.0)
        yawns_recent = self.yawn_detector.get_recent_count(now, window_seconds=60.0)
        head_nods_recent = self.head_nod_detector.get_recent_count(now, window_seconds=60.0)

        # 5.5 CNN Inference (current frame)
        cnn_start_t = time.time()
        cnn_p_sleepy = 0.0
        cnn_latency_ms = 0.0
        if self.cnn_sess and face_detected:
            try:
                # left eye
                left_crop, _ = crop_eye(frame_bgr, landmarks_px, LEFT_EYE)
                res_left_p = 0.0
                if left_crop.size > 0:
                    tensor_l = preprocess_eye_image(left_crop).numpy()
                    logits_l = self.cnn_sess.run(None, {"eye_image": tensor_l})[0]
                    exp_l = np.exp(logits_l - logits_l.max())
                    probs_l = (exp_l / exp_l.sum()).squeeze()
                    res_left_p = float(probs_l[1])

                # right eye
                right_crop, _ = crop_eye(frame_bgr, landmarks_px, RIGHT_EYE)
                res_right_p = 0.0
                if right_crop.size > 0:
                    tensor_r = preprocess_eye_image(right_crop).numpy()
                    logits_r = self.cnn_sess.run(None, {"eye_image": tensor_r})[0]
                    exp_r = np.exp(logits_r - logits_r.max())
                    probs_r = (exp_r / exp_r.sum()).squeeze()
                    res_right_p = float(probs_r[1])
                    
                if debug_mode:
                    if left_crop.size > 0:
                        _, buf = cv2.imencode(".jpg", left_crop)
                        extra_sensors["left_eye_b64"] = base64.b64encode(buf).decode()
                    if right_crop.size > 0:
                        _, buf = cv2.imencode(".jpg", right_crop)
                        extra_sensors["right_eye_b64"] = base64.b64encode(buf).decode()
                    
                    extra_sensors["cnn_p_left"] = res_left_p
                    extra_sensors["cnn_p_right"] = res_right_p

                    from app.drowsiness.face_mesh import draw_landmarks
                    draw_landmarks(annotated, landmarks_px)
                
                avg_sleepy = (res_left_p + res_right_p) / 2.0
                self.cnn_history.append(avg_sleepy)
                cnn_p_sleepy = sum(self.cnn_history) / len(self.cnn_history)
            except Exception as e:
                logger.warning("CNN inference failed on current frame: %s", e)
        
        cnn_latency_ms = (time.time() - cnn_start_t) * 1000.0

        # 5.6 In-Cabin Object & Phone Distraction Detection (Every N frames to preserve 15 FPS real-time speed)
        self._frame_count += 1
        is_ir = (extra_sensors.get("camera_type", "rgb").lower() in ("ir", "infrared", "grayscale"))
        detection_interval = getattr(settings, "DISTRACTION_DETECTION_INTERVAL_FRAMES", 3)
        if (self._frame_count % detection_interval == 1) or (not self._last_all_detections and self._frame_count <= 2):
            try:
                # Detect objects (cell phone and relevant in-cabin objects like bottle, cup, laptop, book)
                self._last_all_detections = self.phone_detector.detect_objects(frame_bgr, is_infrared=is_ir)
                self._last_phone_detections = [d for d in self._last_all_detections if d.get("class_name") == "cell phone"]
            except Exception as e:
                logger.warning("Object detector execution failed on frame: %s", e)
                self._last_all_detections = []
                self._last_phone_detections = []

        phone_present = len(self._last_phone_detections) > 0
        best_phone = self._last_phone_detections[0] if phone_present else None
        phone_conf = best_phone["confidence"] if best_phone else 0.0
        phone_box = best_phone["box"] if best_phone else None

        distraction_res = self.distraction_detector.update(
            now=now,
            phone_detected=phone_present,
            phone_confidence=phone_conf,
            phone_box=phone_box,
            head_pitch_deg=pitch,
            face_detected=True,
            ear=ear,
            is_trip_active=True,
            gaze_info=gaze_info,
            landmarks_px=landmarks_px,
        )

        # 6. Temporal Multi-modal Fusion Engine (Drowsiness)
        self.fusion_engine.register_frame_events(
            perclos=perclos,
            blink_triggered=blink_trig,
            microsleep_triggered=microsleep_trig,
            yawn_triggered=yawn_trig,
            head_nod_triggered=head_nod_trig,
        )

        from app.drowsiness.kss_mapper import is_critical, kss_label, rule_based_kss
        rule_kss = rule_based_kss(
            perclos=perclos,
            blink_rate_per_min=blink_rate,
            microsleep_count_recent=microsleeps_recent,
            yawn_rate_per_min=float(yawns_recent),
            head_nod_events_recent=head_nods_recent,
            sustained_eye_closure_seconds=sustained_closure_s,
            cnn_p_sleepy=cnn_p_sleepy,
        )

        fusion_result = {
            "timestamp": now,
            "face_detected": True,
            "kss_now": rule_kss,
            "kss_label": kss_label(rule_kss),
            "is_critical": is_critical(rule_kss),
            "p_critical_soon": None,
            "score_source": "rule_based_instant",
            "camera_type": extra_sensors.get("camera_type", "rgb"),
            "ear": round(ear, 3),
            "mar": round(mar, 3),
            "pitch": round(pitch, 1),
            "sustained_eye_closure_seconds": round(sustained_closure_s, 2),
            "sustained_yawn_seconds": round(sustained_yawn_s, 2),
            "sustained_nod_seconds": round(sustained_nod_s, 2),
            "cnn_p_sleepy": round(cnn_p_sleepy, 3),
            "raw_signals": {
                "avg_perclos": round(perclos, 3),
                "blink_rate_per_min": blink_rate,
                "microsleeps_in_window": microsleeps_recent,
                "yawns_in_window": yawns_recent,
                "head_nods_in_window": head_nods_recent,
            },
            "extra_sensors": extra_sensors,
        }

        distraction_alert = None
        if distraction_res["triggered"]:
            distraction_alert = {
                "timestamp": now,
                "tier": "warning",
                "level": 2,
                "event_type": "distraction",
                "distraction_type": "phone",
                "duration_seconds": distraction_res["duration_seconds"],
                "message": f"DISTRACTION: Eyes on phone ({distraction_res['duration_seconds']:.1f}s). Keep eyes on the road.",
                "reason": f"Prolonged visual phone distraction sustained for {distraction_res['duration_seconds']:.1f}s (Head Pitch: {pitch:.1f}°)",
                "kss_now": rule_kss,
            }

        # 7. Tiered Alert Evaluation (Drowsiness AlertManager)
        alert = self.alert_manager.evaluate(fusion_result)

        # Distraction alert integration: If no drowsiness alert fired on this frame, surface distraction alert
        if alert is None and distraction_alert is not None:
            alert = distraction_alert

        # 8. Compute risk score, risk level, and contributing factors
        kss_val = fusion_result["kss_now"]
        risk_score = round(min(1.0, max(0.0, (kss_val - 1.0) / 8.0)), 2)

        if alert is not None and alert.get("tier") == "critical":
            risk_level = "CRITICAL"
        elif alert is not None and alert.get("tier") == "warning":
            risk_level = "WARNING"
        elif distraction_res["distraction_confirmed"]:
            risk_level = "WARNING"
        elif alert is not None and alert.get("tier") == "nudge":
            risk_level = "NUDGE"
        elif sustained_closure_s >= 2.5 or (sustained_closure_s >= 1.5 and pitch < config.HEAD_NOD_PITCH_THRESHOLD_DEG):
            risk_level = "CRITICAL"
        elif sustained_closure_s >= 1.8 or sustained_nod_s >= 1.5 or (yawns_recent >= 2 and kss_val >= 6.0):
            risk_level = "WARNING"
        elif sustained_closure_s >= 1.5 or sustained_yawn_s >= 1.5 or perclos >= config.PERCLOS_WARN_THRESHOLD:
            risk_level = "NUDGE"
        else:
            risk_level = "NORMAL"

        factors = []
        if sustained_closure_s >= 1.5:
            factors.append(f"Prolonged eye closure ({sustained_closure_s:.1f}s, EAR: {ear:.2f})")
        if perclos >= config.PERCLOS_WARN_THRESHOLD:
            factors.append(f"Elevated PERCLOS ({(perclos * 100):.1f}%)")
        if sustained_yawn_s >= 1.5 or yawns_recent >= 2:
            factors.append(f"Yawning detected (MAR: {mar:.2f})")
        if pitch < config.HEAD_NOD_PITCH_THRESHOLD_DEG:
            factors.append(f"Forward head nod ({pitch:.1f}°)")
        if distraction_res["distraction_confirmed"]:
            factors.append(f"Visual phone distraction ({distraction_res['duration_seconds']:.1f}s, pitch: {pitch:.1f}°)")
        elif distraction_res["distraction_active"] and distraction_res["duration_seconds"] > 0.5:
            factors.append(f"Looking down toward phone ({distraction_res['duration_seconds']:.1f}s)")

        # Draw annotations onto the frame
        gaze_vert = gaze_info.get("vert_ratio", 0.50) if gaze_info else 0.50
        gaze_dir = gaze_info.get("gaze_direction", "center") if gaze_info else "center"

        cv2.putText(
            annotated,
            f"EAR: {ear:.2f} | MAR: {mar:.2f} | PERCLOS: {perclos*100:.1f}% | KSS: {kss_val:.1f}",
            (15, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (0, 255, 200),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            f"Pitch: {pitch:.1f} deg | Gaze: {gaze_vert:.2f} ({gaze_dir}) | Risk: {risk_level}",
            (15, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (0, 200, 255),
            1,
            cv2.LINE_AA,
        )

        # Draw All Detected In-Cabin Objects with Diagnostic Labels
        for obj in self._last_all_detections:
            box = obj["box"]
            cls_name = obj.get("class_name", "object")
            conf = obj.get("confidence", 0.0)

            if cls_name == "cell phone":
                if distraction_res["distraction_confirmed"]:
                    color = (0, 0, 255)  # Red for confirmed alert
                    thick = 3
                    lbl = f"[ALERT] PHONE {conf*100:.0f}% ({distraction_res['duration_seconds']:.1f}s)"
                elif distraction_res["distraction_active"]:
                    color = (0, 140, 255)  # Orange for accumulating distraction
                    thick = 2
                    lbl = f"[DETECTING] PHONE {conf*100:.0f}% ({distraction_res['duration_seconds']:.1f}s)"
                else:
                    color = (0, 255, 120)  # Green/Cyan: phone present but driver eyes on road
                    thick = 2
                    lbl = f"PHONE {conf*100:.0f}% [EYES ON ROAD]"
            else:
                # Other cabin objects (bottle, cup, laptop, book)
                color = (255, 200, 0)  # Cyan/Sky blue
                thick = 1
                lbl = f"{cls_name.upper()} {conf*100:.0f}%"

            cv2.rectangle(annotated, (box[0], box[1]), (box[2], box[3]), color, thick)
            cv2.putText(
                annotated,
                lbl,
                (box[0], max(16, box[1] - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                color,
                1,
                cv2.LINE_AA,
            )

        # Distraction Status Banner on Overlay
        if distraction_res["distraction_confirmed"]:
            cv2.putText(
                annotated,
                f"DISTRACTION CONFIRMED: Looking at Phone ({distraction_res['duration_seconds']:.1f}s) [BEEPING]",
                (15, 64),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
        elif distraction_res["distraction_active"] and distraction_res["duration_seconds"] > 0.3:
            cv2.putText(
                annotated,
                f"DETECTING DISTRACTION: {distraction_res.get('looking_reason', 'Eyes toward phone')} ({distraction_res['duration_seconds']:.1f}s)",
                (15, 64),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (0, 140, 255),
                1,
                cv2.LINE_AA,
            )
        elif phone_present:
            cv2.putText(
                annotated,
                f"ATTENTIVE: Phone in view but eyes on road (Pitch: {pitch:.1f} deg, Gaze: {gaze_vert:.2f})",
                (15, 64),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (0, 255, 120),
                1,
                cv2.LINE_AA,
            )
        else:
            cv2.putText(
                annotated,
                "STATUS: Safe & Attentive - No Phone in View",
                (15, 64),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.44,
                (180, 180, 180),
                1,
                cv2.LINE_AA,
            )

        metrics = {
            "face_detected": True,
            "ear": round(ear, 3),
            "mar": round(mar, 3),
            "perclos": round(perclos, 3),
            "pitch": round(pitch, 1),
            "head_pitch": round(pitch, 1),
            "yaw": round(yaw, 1),
            "head_yaw": round(yaw, 1),
            "roll": round(roll, 1),
            "head_roll": round(roll, 1),
            "kss": round(kss_val, 1),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "confidence": 0.94,
            "contributing_factors": factors,
            "microsleep_active": sustained_closure_s >= 1.5,
            "yawn_active": sustained_yawn_s >= 1.5,
            "head_nod_active": pitch < config.HEAD_NOD_PITCH_THRESHOLD_DEG,
            "critical_active": bool(self.alert_manager.in_critical_state),
            "phone_detected": phone_present,
            "phone_confidence": phone_conf,
            "phone_box": phone_box,
            "detected_objects": [
                {
                    "class_name": d["class_name"],
                    "confidence": d["confidence"],
                    "box": d["box"],
                }
                for d in self._last_all_detections
            ],
            "gaze": gaze_info,
            "gaze_vert_ratio": gaze_vert,
            "gaze_direction": gaze_dir,
            "distraction_active": distraction_res["distraction_active"],
            "distraction_confirmed": distraction_res["distraction_confirmed"],
            "distraction_duration": distraction_res["duration_seconds"],
            "distraction_triggered": distraction_res["triggered"],
            "distraction_is_new_incident": distraction_res.get("is_new_incident", False),
            "distraction_type": "phone",
            "distraction": distraction_res,
            "distraction_alert": distraction_alert,
            "fusion": fusion_result,
            "landmarks_px": landmarks_px,
            "cnn_latency_ms": round(cnn_latency_ms, 2),
            "total_latency_ms": round((time.time() - frame_start_time) * 1000.0, 2),
            "extra_sensors": extra_sensors,
        }

        return annotated, metrics, alert

    def close(self):
        try:
            self.face_mesh.close()
        except Exception:
            pass


@router.websocket("/ws/monitor/{session_id}")
async def monitor_stream(
    websocket: WebSocket,
    session_id: int,
    token: Optional[str] = None,
    conn=Depends(get_connection),
):
    """
    WebSocket streaming endpoint for real-time driver drowsiness monitoring.
    Receives camera frames directly from the browser client, processes them
    through the modular FYP drowsiness pipeline, and returns real-time telemetry.
    Validates driver session token to prevent unauthorized session access.
    """
    await websocket.accept()

    # 1. Validate session and driver in DB
    m_repo = MonitoringRepository(conn)
    d_repo = DriverRepository(conn)
    v_repo = VehicleRepository(conn)

    session = m_repo.get_session(session_id)
    if not session:
        await websocket.send_json({"error": f"Session {session_id} not found."})
        await websocket.close(code=4004)
        return

    # Check session token if assigned
    if session.session_token:
        # Check token parameter from query string
        if not token or token.strip() != session.session_token.strip():
            logger.warning("Unauthorized WebSocket connection attempt for session %d (invalid/missing token)", session_id)
            await websocket.send_json({"error": "Unauthorized session token."})
            await websocket.close(code=4001)
            return

    if session.status not in ("ACTIVE", "PAUSED"):
        await websocket.send_json({"error": f"Session {session_id} is not active (status: {session.status})."})
        await websocket.close(code=4003)
        return

    driver = d_repo.get_driver_by_id(session.driver_id)
    driver_name = driver.name if driver else f"Driver #{session.driver_id}"

    vehicle_reg = None
    if session.vehicle_id:
        vehicle = v_repo.get_vehicle_by_id(session.vehicle_id)
        if vehicle:
            vehicle_reg = vehicle.registration_number

    processor = DriverSessionProcessor(
        session_id=session_id,
        driver_id=session.driver_id,
        driver_name=driver_name,
        vehicle_reg=vehicle_reg,
    )

    # Initialize live cache entry
    LIVE_SESSION_METRICS[session_id] = {
        "session_id": session_id,
        "driver_id": session.driver_id,
        "driver_name": driver_name,
        "vehicle_registration": vehicle_reg,
        "owner_id": session.owner_id,
        "last_update": time.time(),
        "status": session.status,
        "is_paused": session.status == "PAUSED",
        "metrics": {
            "ear": 0.30,
            "mar": 0.25,
            "perclos": 0.0,
            "head_pitch": 0.0,
            "head_yaw": 0.0,
            "head_roll": 0.0,
            "microsleep_active": False,
            "yawn_active": False,
            "head_nod_active": False,
            "risk_level": "PAUSED" if session.status == "PAUSED" else "NORMAL",
        },
        "fusion": {
            "kss_now": 1.0,
            "kss_label": "Trip Paused" if session.status == "PAUSED" else "Attentive",
            "is_critical": False,
        },
        "latest_alert": None,
    }

    current_distraction_incident_id: Optional[int] = None

    try:
        while True:
            # Receive frame data or action commands from the browser client
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # Drain any backlog messages in the WebSocket buffer to always process the freshest frame
            while True:
                try:
                    next_msg = await asyncio.wait_for(websocket.receive(), timeout=0.0)
                    if next_msg.get("type") == "websocket.disconnect":
                        return
                    message = next_msg
                except (asyncio.TimeoutError, TimeoutError, asyncio.CancelledError):
                    break
                except Exception:
                    break

            # Check if message is a control command (pause / resume)
            if "text" in message and message["text"]:
                raw_text = message["text"].strip()
                if raw_text.startswith("{"):
                    try:
                        payload = json.loads(raw_text)
                        action = payload.get("action")
                        if action == "pause":
                            m_repo.pause_session(session_id)
                            processor.reset_all_detectors()
                            update_live_session_pause_state(session_id, is_paused=True)
                            await websocket.send_json({
                                "session_id": session_id,
                                "status": "PAUSED",
                                "is_paused": True,
                                "driver_name": driver_name,
                                "vehicle_registration": vehicle_reg,
                            })
                            continue
                        elif action == "resume":
                            from app.hardware.alcohol_sensor import mq3_serial_reader
                            if mq3_serial_reader.is_locked():
                                await websocket.send_json({
                                    "error": "VEHICLE OPERATION LOCKED OUT: Potential alcohol detected. Trip resume is restricted pending authorized owner resolution.",
                                    "status": "PAUSED",
                                    "is_paused": True,
                                    "is_locked": True,
                                })
                                continue
                            m_repo.resume_session(session_id)
                            processor.reset_all_detectors()
                            update_live_session_pause_state(session_id, is_paused=False)
                            await websocket.send_json({
                                "session_id": session_id,
                                "status": "ACTIVE",
                                "is_paused": False,
                                "driver_name": driver_name,
                                "vehicle_registration": vehicle_reg,
                            })
                            continue
                    except Exception:
                        pass

            frame_bgr = None
            camera_type = "rgb"
            debug_mode = False
            if "bytes" in message and message["bytes"]:
                # Raw binary frame bytes
                np_arr = np.frombuffer(message["bytes"], np.uint8)
                frame_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            elif "text" in message and message["text"]:
                raw_text = message["text"]
                try:
                    if raw_text.startswith("{"):
                        payload = json.loads(raw_text)
                        b64_str = payload.get("frame") or payload.get("data") or ""
                        camera_type = payload.get("camera_type", "rgb")
                        debug_mode = payload.get("debug_mode", False)
                    else:
                        b64_str = raw_text

                    if "," in b64_str:
                        b64_str = b64_str.split(",", 1)[1]

                    if b64_str:
                        img_bytes = base64.b64decode(b64_str)
                        np_arr = np.frombuffer(img_bytes, np.uint8)
                        frame_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                except Exception as parse_err:
                    logger.warning("Error parsing incoming frame for session %d: %s", session_id, parse_err)
                    continue

            if frame_bgr is None:
                continue

            # Cache the latest clean camera frame for incident evidence capture
            LIVE_SESSION_FRAMES[session_id] = frame_bgr.copy()

            # Check alcohol lockout state
            from app.hardware.alcohol_sensor import mq3_serial_reader
            is_alcohol_locked = mq3_serial_reader.is_locked()

            # Query current session status from DB to ensure instant synchronization with REST endpoints
            db_session = m_repo.get_session(session_id)
            current_status = db_session.status if db_session else "ACTIVE"
            is_paused = (current_status == "PAUSED") or is_alcohol_locked

            if is_alcohol_locked and current_status == "ACTIVE":
                m_repo.pause_session(session_id)
                current_status = "PAUSED"

            if is_paused:
                # Reset detectors continuously while paused to prevent any stale state leak
                processor.reset_all_detectors()
                current_distraction_incident_id = None

                annotated_frame = frame_bgr.copy()
                if is_alcohol_locked:
                    cv2.putText(
                        annotated_frame,
                        "VEHICLE OPERATION RESTRICTED - ALCOHOL LOCKOUT",
                        (15, 35),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.60,
                        (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )
                else:
                    cv2.putText(
                        annotated_frame,
                        "TRIP PAUSED - MONITORING SUSPENDED",
                        (15, 35),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (0, 165, 255),
                        2,
                        cv2.LINE_AA,
                    )

                metrics_to_send = {
                    "face_detected": False,
                    "ear": 0.0,
                    "mar": 0.0,
                    "perclos": 0.0,
                    "pitch": 0.0,
                    "head_pitch": 0.0,
                    "yaw": 0.0,
                    "head_yaw": 0.0,
                    "roll": 0.0,
                    "head_roll": 0.0,
                    "kss": 1.0,
                    "risk_score": 0.0,
                    "risk_level": "RESTRICTED" if is_alcohol_locked else "PAUSED",
                    "confidence": 1.0,
                    "contributing_factors": [
                        "Active MQ-3 alcohol lockout in effect — vehicle operation restricted"
                        if is_alcohol_locked else
                        "Trip is paused — safety monitoring suspended"
                    ],
                    "microsleep_active": False,
                    "yawn_active": False,
                    "head_nod_active": False,
                    "critical_active": False,
                    "phone_detected": False,
                    "phone_confidence": 0.0,
                    "phone_box": None,
                    "distraction_active": False,
                    "distraction_confirmed": False,
                    "distraction_duration": 0.0,
                    "distraction_triggered": False,
                    "distraction_type": "phone",
                    "distraction": {
                        "distraction_active": False,
                        "distraction_confirmed": False,
                        "triggered": False,
                        "duration_seconds": 0.0,
                        "cooldown_active": False,
                        "looking_down": False,
                        "phone_present": False,
                        "distraction_type": "phone",
                    },
                    "distraction_alert": None,
                }
                fusion_to_send = {
                    "timestamp": time.time(),
                    "kss_now": 1.0,
                    "kss_label": "Operation Restricted" if is_alcohol_locked else "Trip Paused",
                    "is_critical": False,
                    "p_critical_soon": None,
                    "score_source": "alcohol_lockout" if is_alcohol_locked else "paused",
                    "raw_signals": {
                        "avg_perclos": 0.0,
                        "blink_rate_per_min": 0.0,
                        "microsleeps_in_window": 0,
                        "yawns_in_window": 0,
                        "head_nods_in_window": 0,
                    },
                }

                _, buffer = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                frame_b64 = base64.b64encode(buffer).decode("utf-8")

                ws_message = {
                    "session_id": session_id,
                    "status": "PAUSED",
                    "is_paused": True,
                    "is_locked": is_alcohol_locked,
                    "critical_active": False,
                    "driver_id": session.driver_id,
                    "driver_name": driver_name,
                    "vehicle_registration": vehicle_reg,
                    "frame_b64": frame_b64,
                    "metrics": metrics_to_send,
                    "fusion": fusion_to_send,
                    "alert": None,
                    "distraction": metrics_to_send["distraction"],
                    "distraction_active": False,
                    "distraction_confirmed": False,
                    "phone_detected": False,
                }

                LIVE_SESSION_METRICS[session_id] = {
                    "session_id": session_id,
                    "status": "PAUSED",
                    "is_paused": True,
                    "is_locked": is_alcohol_locked,
                    "critical_active": False,
                    "driver_id": session.driver_id,
                    "driver_name": driver_name,
                    "vehicle_registration": vehicle_reg,
                    "owner_id": session.owner_id,
                    "last_update": time.time(),
                    "metrics": metrics_to_send,
                    "fusion": fusion_to_send,
                    "latest_alert": None,
                }

                await websocket.send_json(ws_message)
                continue

            # When RUNNING: Process frame through full FYP drowsiness engine pipeline
            extra_sensors = {"camera_type": camera_type}
            annotated_frame, metrics, alert = processor.process_frame(frame_bgr, extra_sensors=extra_sensors, debug_mode=debug_mode)
            is_critical_active = bool(processor.alert_manager.in_critical_state)

            # Reset active distraction incident ID tracking when distraction has recovered
            if not metrics.get("distraction_confirmed"):
                current_distraction_incident_id = None

            dist_info = metrics.get("distraction", {})

            # 1. Distraction Incident Persistence: Exactly ONE database record per continuous episode
            distraction_evidence_path = None
            if dist_info.get("is_new_incident"):
                try:
                    distraction_evidence_path = generate_evidence_screenshot(
                        frame_bgr=annotated_frame,
                        driver_name=driver_name,
                        driver_id=session.driver_id,
                        vehicle_registration=vehicle_reg,
                        session_id=session_id,
                        event_type="distraction",
                        alert_level=2,
                        ear=metrics["ear"],
                        mar=metrics["mar"],
                        perclos=metrics["perclos"],
                        head_pose={"pitch": metrics["head_pitch"], "yaw": metrics["head_yaw"], "roll": metrics["head_roll"]},
                        kss_score=metrics["fusion"]["kss_now"],
                        kss_label="Distracted (Phone)",
                        landmarks_px=metrics.get("landmarks_px"),
                        trigger_reason=f"Visual phone distraction sustained for {dist_info.get('duration_seconds', 2.0):.1f}s",
                    )
                except Exception as ev_err:
                    logger.warning("Could not generate distraction evidence screenshot: %s", ev_err)

                try:
                    repo = MonitoringRepository(conn)
                    current_distraction_incident_id = repo.create_incident(
                        session_id=session_id,
                        driver_id=session.driver_id,
                        vehicle_id=session.vehicle_id,
                        event_type="distraction",
                        alert_level=2,
                        kss_score=metrics["fusion"]["kss_now"],
                        ear=metrics["ear"],
                        mar=metrics["mar"],
                        perclos=metrics["perclos"],
                        head_pitch_deg=metrics["head_pitch"],
                        evidence_path=distraction_evidence_path,
                        owner_id=session.owner_id,
                        distraction_type="phone",
                        duration_seconds=dist_info.get("duration_seconds"),
                    )
                    logger.info(
                        "Persisted distraction incident #%s for session %s (driver %s, duration: %.1fs, evidence: %s)",
                        current_distraction_incident_id,
                        session_id,
                        session.driver_id,
                        dist_info.get("duration_seconds", 0.0),
                        distraction_evidence_path,
                    )
                except Exception as db_err:
                    logger.error(
                        "DATABASE ERROR: Failed to insert distraction incident for session %s: %s",
                        session_id,
                        db_err,
                        exc_info=True,
                    )

            # 2. Distraction Audio Beep: Beep on first confirmation AND repeat every 5s during sustained distraction
            if dist_info.get("triggered"):
                trigger_distraction_beep()

            # 3. Handle alert payload for UI notification and drowsiness DB persistence
            alert_payload = None
            if alert is not None:
                tier = alert.get("tier", "warning")
                event_type = alert.get("event_type", tier)
                alert_level = alert.get("level", 1 if tier == "nudge" else (2 if tier == "warning" else 3))
                evidence_rel_path = None
                incident_id = None
                trigger_reason = alert.get("reason", "Severe safety alert detected")

                if event_type == "distraction":
                    # Reuse the incident_id already created for this episode to prevent duplicate DB records on repeated beeps
                    incident_id = current_distraction_incident_id
                    evidence_rel_path = distraction_evidence_path
                else:
                    # Drowsiness alert (nudge, warning, critical)
                    if alert_level == 3:
                        evidence_rel_path = generate_evidence_screenshot(
                            frame_bgr=frame_bgr,
                            driver_name=driver_name,
                            driver_id=session.driver_id,
                            vehicle_registration=vehicle_reg,
                            session_id=session_id,
                            event_type=tier,
                            alert_level=alert_level,
                            ear=metrics["ear"],
                            mar=metrics["mar"],
                            perclos=metrics["perclos"],
                            head_pose={"pitch": metrics["head_pitch"], "yaw": metrics["head_yaw"], "roll": metrics["head_roll"]},
                            kss_score=metrics["fusion"]["kss_now"],
                            kss_label=metrics["fusion"]["kss_label"],
                            landmarks_px=metrics.get("landmarks_px"),
                            trigger_reason=trigger_reason,
                        )

                    try:
                        repo = MonitoringRepository(conn)
                        incident_id = repo.create_incident(
                            session_id=session_id,
                            driver_id=session.driver_id,
                            vehicle_id=session.vehicle_id,
                            event_type=event_type,
                            alert_level=alert_level,
                            kss_score=metrics["fusion"]["kss_now"],
                            ear=metrics["ear"],
                            mar=metrics["mar"],
                            perclos=metrics["perclos"],
                            head_pitch_deg=metrics["head_pitch"],
                            evidence_path=evidence_rel_path,
                            owner_id=session.owner_id,
                            distraction_type=alert.get("distraction_type"),
                            duration_seconds=alert.get("duration_seconds"),
                        )
                    except Exception as db_err:
                        logger.error(
                            "DATABASE ERROR: Failed to insert drowsiness incident for session %s: %s",
                            session_id,
                            db_err,
                            exc_info=True,
                        )

                alert_payload = {
                    "incident_id": incident_id,
                    "tier": tier,
                    "level": alert_level,
                    "event_type": event_type,
                    "distraction_type": alert.get("distraction_type"),
                    "duration_seconds": alert.get("duration_seconds"),
                    "message": alert["message"],
                    "reason": trigger_reason,
                    "kss_now": alert["kss_now"],
                    "evidence_path": evidence_rel_path,
                    "timestamp": alert["timestamp"],
                }

            # Encode annotated frame as base64 JPEG for WebSocket transport back to UI
            _, buffer = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            frame_b64 = base64.b64encode(buffer).decode("utf-8")

            # Clean landmarks array from metrics before sending JSON
            metrics_to_send = {k: v for k, v in metrics.items() if k != "landmarks_px"}

            debug_data = None
            if debug_mode:
                debug_data = {
                    "left_eye": metrics["extra_sensors"].get("left_eye_b64"),
                    "right_eye": metrics["extra_sensors"].get("right_eye_b64"),
                    "cnn_p_left": metrics["extra_sensors"].get("cnn_p_left"),
                    "cnn_p_right": metrics["extra_sensors"].get("cnn_p_right"),
                }

            ws_message = {
                "session_id": session_id,
                "status": "ACTIVE",
                "is_paused": False,
                "is_locked": False,
                "critical_active": is_critical_active,
                "camera_type": camera_type,
                "driver_id": session.driver_id,
                "driver_name": driver_name,
                "vehicle_registration": vehicle_reg,
                "frame_b64": frame_b64,
                "metrics": metrics_to_send,
                "fusion": metrics["fusion"],
                "alert": alert_payload,
                "debug_data": debug_data,
                "distraction": metrics_to_send.get("distraction"),
                "distraction_active": metrics_to_send.get("distraction_active", False),
                "distraction_confirmed": metrics_to_send.get("distraction_confirmed", False),
                "phone_detected": metrics_to_send.get("phone_detected", False),
            }

            # Update live cache for Owner Portal
            LIVE_SESSION_METRICS[session_id] = {
                "session_id": session_id,
                "status": "ACTIVE",
                "is_paused": False,
                "is_locked": False,
                "critical_active": is_critical_active,
                "driver_id": session.driver_id,
                "driver_name": driver_name,
                "vehicle_registration": vehicle_reg,
                "owner_id": session.owner_id,
                "last_update": time.time(),
                "metrics": metrics_to_send,
                "fusion": metrics["fusion"],
                "latest_alert": alert_payload,
            }

            await websocket.send_json(ws_message)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %d", session_id)
    except Exception as e:
        logger.error("Error in monitoring stream for session %d: %s", session_id, e, exc_info=True)
    finally:
        # Cleanup
        if session_id in LIVE_SESSION_METRICS:
            LIVE_SESSION_METRICS.pop(session_id, None)
        if session_id in LIVE_SESSION_FRAMES:
            LIVE_SESSION_FRAMES.pop(session_id, None)

        if processor:
            processor.close()

        # Mark session as INTERRUPTED if it's still ACTIVE in DB
        # (handles browser tab close without pressing End Trip; leaves PAUSED sessions intact)
        try:
            cleanup_repo = MonitoringRepository(conn)
            session_record = cleanup_repo.get_session(session_id)
            if session_record and session_record.status == "ACTIVE":
                cleanup_repo.end_session(session_id, status="INTERRUPTED")
                cleanup_repo.recalculate_safety_rating(session_record.driver_id)
                logger.info("Session %d marked as INTERRUPTED (unexpected disconnect)", session_id)
        except Exception as cleanup_err:
            logger.warning("Failed to mark session %d as interrupted: %s", session_id, cleanup_err)
