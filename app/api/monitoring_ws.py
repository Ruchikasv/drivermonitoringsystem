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
- Enforced single-camera acquisition lock
"""

import asyncio
import base64
import logging
import time
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.vehicle_repository import VehicleRepository
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

# Global camera lock to prevent concurrent device access
_camera_lock = asyncio.Lock()
_active_camera_session: Optional[int] = None

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
        self.face_mesh = FaceMeshDetector()
        self.perclos_tracker = PerclosTracker()
        self.microsleep_det = MicrosleepDetector()
        self.yawn_det = YawnDetector()
        self.head_nod_det = HeadNodDetector()
        self.fusion = FusionEngine()
        self.alert_mgr = AlertManager()

        self.last_fusion_result: Optional[dict] = None

    def process_frame(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, dict, Optional[dict]]:
        """
        Process a single BGR video frame.

        Returns
        -------
        tuple[np.ndarray, dict, Optional[dict]]
            (annotated_frame_bgr, metrics_dict, alert_dict_or_None)
        """
        now = time.time()
        annotated = frame_bgr.copy()
        h, w = frame_bgr.shape[:2]

        landmarks_px, _ = self.face_mesh.process(frame_bgr)
        face_detected = landmarks_px is not None

        ear_metrics = {"avg_ear": 0.0, "left_ear": 0.0, "right_ear": 0.0, "mar": 0.0}
        head_pose = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0, "valid": False}
        perclos = 0.0
        blink_trig = False
        ms_trig = False
        yawn_trig = False
        nod_trig = False

        if face_detected:
            # 1. EAR & MAR
            ear_metrics = compute_eye_mouth_metrics(landmarks_px)

            # 2. PERCLOS
            perclos, blink_trig = self.perclos_tracker.update(ear_metrics["avg_ear"], now=now)

            # 3. Head Pose
            head_pose = estimate_head_pose(landmarks_px, frame_bgr.shape)

            # 4. Sustained condition detectors
            ms_trig = self.microsleep_det.update(ear_metrics["avg_ear"], now=now)
            yawn_trig = self.yawn_det.update(ear_metrics["mar"], now=now)
            nod_trig = self.head_nod_det.update(head_pose["pitch"], now=now)

            # 5. Draw face bounding rectangle and landmarks highlight
            x_min = max(0, int(np.min(landmarks_px[:, 0])))
            y_min = max(0, int(np.min(landmarks_px[:, 1])))
            x_max = min(w - 1, int(np.max(landmarks_px[:, 0])))
            y_max = min(h - 1, int(np.max(landmarks_px[:, 1])))
            cv2.rectangle(annotated, (x_min, y_min), (x_max, y_max), (0, 220, 100), 1)

            # Draw key facial points (eyes, mouth contour)
            for idx in [33, 133, 362, 263, 61, 291, 1, 152]:
                px = int(landmarks_px[idx][0])
                py = int(landmarks_px[idx][1])
                cv2.circle(annotated, (px, py), 2, (0, 255, 255), -1)

        # 6. Fusion Engine registration & aggregation
        self.fusion.register_frame_events(
            perclos=perclos,
            blink_triggered=blink_trig,
            microsleep_triggered=ms_trig,
            yawn_triggered=yawn_trig,
            head_nod_triggered=nod_trig,
        )

        agg = self.fusion.maybe_aggregate(now=now)
        if agg is not None:
            self.last_fusion_result = agg

        current_fusion = self.last_fusion_result or {
            "timestamp": now,
            "kss_now": 1.0,
            "kss_label": "Extremely alert",
            "is_critical": False,
            "p_critical_soon": None,
            "prediction_horizon_seconds": 300.0,
            "score_source": "initialising",
            "raw_signals": {
                "avg_perclos": perclos,
                "blink_rate_per_min": 0.0,
                "microsleeps_in_window": 0,
                "yawn_rate_per_min": 0.0,
                "head_nods_in_window": 0,
            },
        }

        # 7. Alert Manager evaluation
        alert = None
        if self.last_fusion_result is not None:
            alert = self.alert_mgr.evaluate(self.last_fusion_result)

        metrics = {
            "face_detected": face_detected,
            "ear": round(ear_metrics["avg_ear"], 3),
            "mar": round(ear_metrics["mar"], 3),
            "perclos": round(perclos, 3),
            "head_pitch": round(head_pose["pitch"], 1),
            "head_yaw": round(head_pose["yaw"], 1),
            "head_roll": round(head_pose["roll"], 1),
            "microsleep_active": self.microsleep_det.is_condition_active(),
            "yawn_active": self.yawn_det.is_condition_active(),
            "head_nod_active": self.head_nod_det.is_condition_active(),
            "fusion": current_fusion,
            "landmarks_px": landmarks_px,
        }

        return annotated, metrics, alert

    def close(self):
        try:
            self.face_mesh.close()
        except Exception:
            pass


@router.websocket("/ws/monitor/{session_id}")
async def monitor_stream(websocket: WebSocket, session_id: int):
    """
    WebSocket streaming endpoint for real-time monitoring.
    """
    global _active_camera_session

    await websocket.accept()

    # 1. Validate session and driver in DB
    conn = get_connection()
    try:
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
    finally:
        conn.close()

    # 2. Acquire camera lock
    if _camera_lock.locked() or _active_camera_session is not None:
        await websocket.send_json({
            "error": "Camera is currently in use by another session. Please end the other session first."
        })
        await websocket.close(code=4009)
        return

    await _camera_lock.acquire()
    _active_camera_session = session_id

    cap = None
    processor = None

    try:
        # Open hardware camera
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            # Try camera index 1 if 0 fails
            cap.release()
            cap = cv2.VideoCapture(1)

        if not cap.isOpened():
            await websocket.send_json({"error": "Unable to access webcam device. Please check hardware permissions."})
            await websocket.close(code=4008)
            return

        # Optimize camera resolution and buffer
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        processor = DriverSessionProcessor(
            session_id=session_id,
            driver_id=session.driver_id,
            driver_name=driver_name,
            vehicle_reg=vehicle_reg,
        )

        frame_delay = 1.0 / max(5, min(30, settings.MONITORING_FPS))

        while True:
            t0 = time.time()

            ret, frame = cap.read()
            if not ret or frame is None:
                await asyncio.sleep(0.05)
                continue

            # Process frame through full fyp pipeline
            annotated_frame, metrics, alert = processor.process_frame(frame)

            # Handle alert trigger and evidence capture
            alert_payload = None
            if alert is not None:
                tier = alert["tier"]
                alert_level = 1 if tier == "nudge" else (2 if tier == "warning" else 3)

                # Generate styled composite evidence screenshot
                evidence_rel_path = generate_evidence_screenshot(
                    frame_bgr=frame,
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
                )

                # Persist incident to SQLite
                db_conn = get_connection()
                try:
                    repo = MonitoringRepository(db_conn)
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
                finally:
                    db_conn.close()

                alert_payload = {
                    "incident_id": incident_id,
                    "tier": tier,
                    "level": alert_level,
                    "message": alert["message"],
                    "kss_now": alert["kss_now"],
                    "evidence_path": evidence_rel_path,
                    "timestamp": alert["timestamp"],
                }

            # Encode annotated frame as base64 JPEG for WebSocket transport
            _, buffer = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
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

            # Throttle loop to target FPS
            elapsed = time.time() - t0
            sleep_time = max(0.001, frame_delay - elapsed)
            await asyncio.sleep(sleep_time)

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

        if cap is not None and cap.isOpened():
            cap.release()

        _active_camera_session = None
        if _camera_lock.locked():
            _camera_lock.release()
