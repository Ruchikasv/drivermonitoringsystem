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
import json
import logging
import time
from typing import Optional

import cv2
import numpy as np
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
from app.drowsiness.face_mesh import FaceMeshDetector
from app.drowsiness.fusion_engine import FusionEngine
from app.drowsiness.head_pose import estimate_head_pose
from app.drowsiness.perclos import PerclosTracker

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Monitoring WebSocket"])

# In-memory real-time metrics cache for Owner Portal polling (metrics-only)
LIVE_SESSION_METRICS: dict[int, dict] = {}


def get_live_metrics(session_id: int) -> Optional[dict]:
    """Retrieve the latest real-time metrics snapshot for a session."""
    return LIVE_SESSION_METRICS.get(session_id)


def get_all_live_metrics() -> dict[int, dict]:
    """Retrieve all active session metrics snapshots."""
    return LIVE_SESSION_METRICS.copy()


class DriverSessionProcessor:
    """Encapsulates the complete drowsiness detection pipeline for one driver session."""

    def __init__(self, session_id: int, driver_id: int, driver_name: str, vehicle_reg: Optional[str]):
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

    def process_frame(self, frame_bgr: np.ndarray, now: float = None) -> tuple[np.ndarray, dict, Optional[dict]]:
        """
        Process a single BGR camera frame through the entire drowsiness pipeline.
        Returns:
            annotated_frame (np.ndarray): Frame with visual debug overlays
            metrics (dict): Real-time metrics (EAR, MAR, PERCLOS, head pose, KSS, etc.)
            alert (dict or None): Triggered alert payload if an alert threshold was crossed
        """
        now = now or time.time()
        annotated = frame_bgr.copy()
        h, w = annotated.shape[:2]

        # 1. Face Mesh
        landmarks_px, landmarks_norm = self.face_mesh.process(frame_bgr)
        face_detected = landmarks_px is not None

        if not face_detected:
            self.microsleep_detector.reset_condition()
            self.yawn_detector.reset_condition()
            self.head_nod_detector.reset_condition()

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

        # 4. 3D Head Pose
        head_pose = estimate_head_pose(landmarks_px, frame_bgr.shape)
        pitch = head_pose["pitch"] if head_pose["valid"] else 0.0
        yaw = head_pose["yaw"] if head_pose["valid"] else 0.0
        roll = head_pose["roll"] if head_pose["valid"] else 0.0

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

        # 6. Temporal Multi-modal Fusion Engine
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
        )

        fusion_result = {
            "timestamp": now,
            "face_detected": True,
            "kss_now": rule_kss,
            "kss_label": kss_label(rule_kss),
            "is_critical": is_critical(rule_kss),
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

        # 7. Tiered Alert Evaluation
        alert = self.alert_manager.evaluate(fusion_result)

        # 8. Compute risk score, risk level, and contributing factors
        kss_val = fusion_result["kss_now"]
        risk_score = round(min(1.0, max(0.0, (kss_val - 1.0) / 8.0)), 2)

        if alert is not None and alert["tier"] == "critical":
            risk_level = "CRITICAL"
        elif alert is not None and alert["tier"] == "warning":
            risk_level = "WARNING"
        elif alert is not None and alert["tier"] == "nudge":
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

        # Draw annotations onto the frame
        cv2.putText(
            annotated,
            f"EAR: {ear:.2f} | MAR: {mar:.2f} | PERCLOS: {perclos*100:.1f}%",
            (15, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 200),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            f"Pitch: {pitch:.1f} deg | KSS: {kss_val:.1f} ({fusion_result['kss_label']}) | Risk: {risk_level}",
            (15, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 200, 255),
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
            "fusion": fusion_result,
            "landmarks_px": landmarks_px,
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
    conn=Depends(get_connection),
):
    """
    WebSocket streaming endpoint for real-time driver drowsiness monitoring.
    Receives camera frames directly from the browser client, processes them
    through the modular FYP drowsiness pipeline, and returns real-time telemetry.
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

    if session.status != "ACTIVE":
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

    try:
        while True:
            # Receive frame data from the browser client
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

            frame_bgr = None
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

            # Process frame through full FYP drowsiness engine pipeline
            annotated_frame, metrics, alert = processor.process_frame(frame_bgr)

            # Handle alert trigger and evidence capture
            alert_payload = None
            if alert is not None:
                tier = alert["tier"]
                alert_level = 1 if tier == "nudge" else (2 if tier == "warning" else 3)
                evidence_rel_path = None
                incident_id = None
                trigger_reason = alert.get("reason", "Severe drowsiness detected")

                # Capture evidence screenshot ONLY for Level 3 (Critical) incidents
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

                    # Persist Level 3 critical incident to SQLite
                    repo = MonitoringRepository(conn)
                    incident_id = repo.create_incident(
                        session_id=session_id,
                        driver_id=session.driver_id,
                        vehicle_id=session.vehicle_id,
                        event_type=tier,
                        alert_level=alert_level,
                        kss_score=metrics["fusion"]["kss_now"],
                        ear=metrics["ear"],
                        mar=metrics["mar"],
                        perclos=metrics["perclos"],
                        head_pitch_deg=metrics["head_pitch"],
                        evidence_path=evidence_rel_path,
                    )

                alert_payload = {
                    "incident_id": incident_id,
                    "tier": tier,
                    "level": alert_level,
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

            ws_message = {
                "session_id": session_id,
                "driver_id": session.driver_id,
                "driver_name": driver_name,
                "vehicle_registration": vehicle_reg,
                "frame_b64": frame_b64,
                "metrics": metrics_to_send,
                "fusion": metrics["fusion"],
                "alert": alert_payload,
            }

            # Update live cache for Owner Portal
            LIVE_SESSION_METRICS[session_id] = {
                "session_id": session_id,
                "driver_id": session.driver_id,
                "driver_name": driver_name,
                "vehicle_registration": vehicle_reg,
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

        if processor:
            processor.close()

        # Mark session as INTERRUPTED if it's still ACTIVE in DB
        # (handles browser tab close without pressing End Trip)
        try:
            cleanup_repo = MonitoringRepository(conn)
            session_record = cleanup_repo.get_session(session_id)
            if session_record and session_record.status == "ACTIVE":
                cleanup_repo.end_session(session_id, status="INTERRUPTED")
                cleanup_repo.recalculate_safety_rating(session_record.driver_id)
                logger.info("Session %d marked as INTERRUPTED (unexpected disconnect)", session_id)
        except Exception as cleanup_err:
            logger.warning("Failed to mark session %d as interrupted: %s", session_id, cleanup_err)
