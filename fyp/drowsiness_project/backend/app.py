"""
NeuraDrive backend entrypoint.

Runs the full pipeline:
  webcam frame -> FaceMesh -> EAR/MAR + PERCLOS + head pose
                -> event detectors (microsleep / yawn / head-nod, time-based)
                -> FusionEngine (rule-based + LSTM prediction)
                -> AlertManager (tiered alerts, logged incidents)
  and streams annotated frames + live metrics to the browser dashboard over
  a WebSocket, plus exposes REST endpoints for incident history, CSV export,
  and health.

Run with:  python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
(use `python -m uvicorn`, not a bare `uvicorn`, so it always uses your
active virtualenv's interpreter -- see README troubleshooting)
"""

import asyncio
import base64
import csv
import io
import json
import os
import time

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core import config
from core.face_mesh import FaceMeshDetector
from core.ear_mar import compute_eye_mouth_metrics
from core.perclos import PerclosTracker
from core.head_pose import estimate_head_pose
from core.event_detectors import SustainedConditionDetector
from core.fusion_engine import FusionEngine
from core.alert_manager import AlertManager

app = FastAPI(title="NeuraDrive Driver State Intelligence API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


# ---------------------------------------------------------------------------
# Pipeline state (single-driver session; simple by design for a laptop demo)
# ---------------------------------------------------------------------------
class DriverSession:
    def __init__(self):
        self.face_mesh = FaceMeshDetector()
        self.perclos_tracker = PerclosTracker(
            ear_threshold=config.EAR_THRESHOLD,
            window_seconds=config.PERCLOS_WINDOW_SECONDS,
        )
        self.microsleep_detector = SustainedConditionDetector(
            min_duration_seconds=config.MICROSLEEP_MIN_DURATION_SECONDS,
            cooldown_seconds=config.MICROSLEEP_COOLDOWN_SECONDS,
        )
        self.yawn_detector = SustainedConditionDetector(
            min_duration_seconds=config.YAWN_MIN_DURATION_SECONDS,
            cooldown_seconds=config.YAWN_COOLDOWN_SECONDS,
        )
        self.head_nod_detector = SustainedConditionDetector(
            min_duration_seconds=config.HEAD_NOD_MIN_DURATION_SECONDS,
            cooldown_seconds=config.HEAD_NOD_COOLDOWN_SECONDS,
        )
        self.fusion = FusionEngine()
        self.alerts = AlertManager()

        self.latest_fusion_result = None
        self.latest_alert = None

    def process_frame(self, frame_bgr: np.ndarray) -> dict:
        landmarks_px, _landmarks_norm = self.face_mesh.process(frame_bgr)

        overlay = frame_bgr.copy()
        frame_metrics = {"face_found": landmarks_px is not None}
        now = time.time()

        if landmarks_px is not None:
            metrics = compute_eye_mouth_metrics(landmarks_px)
            perclos_out = self.perclos_tracker.update(metrics["avg_ear"], timestamp=now)
            pose = estimate_head_pose(landmarks_px, frame_bgr.shape)

            # Microsleep requires BOTH eyes individually below threshold
            # (not the average) so a single occluded/misread eye during a
            # head turn can't falsely trigger it, sustained for a real
            # duration in seconds rather than a frame count.
            both_eyes_closed = (metrics["left_ear"] < config.EAR_THRESHOLD and
                                 metrics["right_ear"] < config.EAR_THRESHOLD)
            microsleep_triggered = self.microsleep_detector.update(both_eyes_closed, now)

            yawn_triggered = self.yawn_detector.update(
                metrics["mar"] > config.MAR_THRESHOLD, now)

            head_nod_now = pose["valid"] and abs(pose["pitch"]) > config.HEAD_NOD_PITCH_THRESHOLD_DEG
            head_nod_triggered = self.head_nod_detector.update(head_nod_now, now)

            self.fusion.register_frame_events(
                perclos=perclos_out["perclos"],
                blink_triggered=perclos_out["blink_triggered"],
                microsleep_triggered=microsleep_triggered,
                yawn_triggered=yawn_triggered,
                head_nod_triggered=head_nod_triggered,
            )

            fusion_result = self.fusion.maybe_aggregate(now=now)
            if fusion_result is not None:
                self.latest_fusion_result = fusion_result
                alert = self.alerts.evaluate(fusion_result)
                if alert is not None:
                    self.latest_alert = alert

            frame_metrics.update({
                "ear": round(metrics["avg_ear"], 3),
                "left_ear": round(metrics["left_ear"], 3),
                "right_ear": round(metrics["right_ear"], 3),
                "mar": round(metrics["mar"], 3),
                "perclos": round(perclos_out["perclos"], 3),
                "is_eye_closed": perclos_out["is_eye_closed"],
                "head_pitch_deg": round(pose["pitch"], 1) if pose["valid"] else None,
            })
            overlay = _draw_overlay(overlay, landmarks_px, frame_metrics)

        _, buf = cv2.imencode(".jpg", overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        frame_b64 = base64.b64encode(buf).decode("utf-8")

        return {
            "frame_jpeg_b64": frame_b64,
            "frame_metrics": frame_metrics,
            "fusion": self.latest_fusion_result,
            "alert": self.latest_alert,
        }


def _draw_overlay(frame, landmarks_px, metrics: dict):
    for (x, y) in landmarks_px[::4].astype(int):  # sparse dots, cheap to draw
        cv2.circle(frame, (x, y), 1, (0, 255, 120), -1)
    y0 = 24
    lines = [
        f"EAR: {metrics.get('ear')} (L {metrics.get('left_ear')} / R {metrics.get('right_ear')})",
        f"MAR: {metrics.get('mar')}   PERCLOS: {metrics.get('perclos')}",
        f"Head pitch: {metrics.get('head_pitch_deg')} deg",
    ]
    for i, line in enumerate(lines):
        cv2.putText(frame, line, (10, y0 + i * 22), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def _synthetic_frame(t: float) -> np.ndarray:
    """Fallback frame generator used only when no webcam is available, so
    the pipeline can still be smoke-tested end to end (e.g. in CI or a
    sandboxed environment). Draws a simple animated face-like shape; it will
    NOT produce meaningful drowsiness metrics -- it exists purely to prove
    the plumbing (capture -> process -> stream) works without a camera."""
    frame = np.full((config.FRAME_HEIGHT, config.FRAME_WIDTH, 3), 40, dtype=np.uint8)
    cx, cy = config.FRAME_WIDTH // 2, config.FRAME_HEIGHT // 2
    cv2.putText(frame, "NO CAMERA - SYNTHETIC FALLBACK FRAME", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.circle(frame, (cx, cy), 90, (200, 180, 160), -1)
    blink = (int(t * 2) % 6 == 0)
    eye_h = 2 if blink else 10
    cv2.ellipse(frame, (cx - 30, cy - 15), (14, eye_h), 0, 0, 360, (30, 30, 30), -1)
    cv2.ellipse(frame, (cx + 30, cy - 15), (14, eye_h), 0, 0, 360, (30, 30, 30), -1)
    return frame


session = DriverSession()


@app.get("/")
def root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"status": "NeuraDrive backend running. Frontend not found."})


@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": session.fusion.model is not None}


@app.get("/api/incidents")
def incidents():
    path = session.alerts.log_path
    if not os.path.exists(path):
        return {"incidents": []}
    with open(path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    return {"incidents": lines[-200:]}


@app.get("/api/incidents/csv")
def incidents_csv():
    """Downloadable CSV of every logged drowsiness incident this session --
    used by the frontend's 'Download Incident Log' button."""
    path = session.alerts.log_path
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            rows = [json.loads(line) for line in f if line.strip()]

    buf = io.StringIO()
    fieldnames = ["timestamp", "datetime", "tier", "message", "kss_now",
                  "p_critical_soon", "gps_lat", "gps_lon", "sos_email_sent"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        gps = r.get("gps") or {}
        writer.writerow({
            "timestamp": r.get("timestamp"),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.get("timestamp", 0))),
            "tier": r.get("tier"),
            "message": r.get("message"),
            "kss_now": r.get("kss_now"),
            "p_critical_soon": r.get("p_critical_soon"),
            "gps_lat": gps.get("lat"),
            "gps_lon": gps.get("lon"),
            "sos_email_sent": r.get("sos_email_sent"),
        })
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=neuradrive_incident_log.csv"},
    )


@app.websocket("/ws/stream")
async def stream(websocket: WebSocket):
    await websocket.accept()
    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    use_synthetic = not cap.isOpened()
    if use_synthetic and not config.FALLBACK_TO_SYNTHETIC_IF_NO_CAMERA:
        await websocket.send_text(json.dumps({"error": "No camera available."}))
        await websocket.close()
        return

    try:
        t0 = time.time()
        while True:
            if use_synthetic:
                frame = _synthetic_frame(time.time() - t0)
            else:
                ok, frame = cap.read()
                if not ok:
                    await asyncio.sleep(0.05)
                    continue
                frame = cv2.resize(frame, (config.FRAME_WIDTH, config.FRAME_HEIGHT))

            payload = session.process_frame(frame)
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1.0 / config.TARGET_FPS)
    except WebSocketDisconnect:
        pass
    finally:
        if cap.isOpened():
            cap.release()


# Serve static frontend assets (css/js) if present
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
