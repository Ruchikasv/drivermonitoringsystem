import asyncio
import json
import logging
import time
import base64
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.monitoring_ws import DriverSessionProcessor
from app.drowsiness.fusion_engine import FusionEngine
from app.drowsiness.alert_manager import AlertManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Simulation WebSocket"])

@router.websocket("/ws/simulate/{session_id}")
async def simulation_websocket_endpoint(websocket: WebSocket, session_id: int):
    await websocket.accept()
    logger.info(f"Video-Based Simulation WS connected for session {session_id}")
    
    # We use fake session/driver IDs for the simulation
    processor = DriverSessionProcessor(session_id=session_id, driver_id=999, driver_name="Sim Driver", vehicle_reg="SIM-001")
    is_paused = False
    
    try:
        while True:
            try:
                # Receive message
                message = await websocket.receive()
                
                frame_bgr = None
                sensors = {}
                
                if "bytes" in message and message["bytes"]:
                    np_arr = np.frombuffer(message["bytes"], np.uint8)
                    frame_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                elif "text" in message and message["text"]:
                    raw_text = message["text"]
                    if raw_text.startswith("{"):
                        data = json.loads(raw_text)
                        
                        if data.get("type") == "PAUSE":
                            is_paused = True
                            continue
                        elif data.get("type") == "RESUME":
                            is_paused = False
                            continue
                        elif data.get("type") == "SET_SCENARIO":
                            scenario = data.get("scenario", "NORMAL")
                            if scenario == "WEBSOCKET DISCONNECT/RECONNECT":
                                await websocket.close()
                                return
                            # Reset state when scenario changes
                            processor.reset_all_detectors()
                            await websocket.send_json({"type": "SCENARIO_UPDATED", "scenario": scenario})
                            continue
                            
                        b64_str = data.get("frame", "")
                        sensors = data.get("sensors", {})
                    else:
                        b64_str = raw_text
                        sensors = {}

                    if b64_str:
                        if "," in b64_str:
                            b64_str = b64_str.split(",", 1)[1]
                        img_bytes = base64.b64decode(b64_str)
                        np_arr = np.frombuffer(img_bytes, np.uint8)
                        frame_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                
                if is_paused:
                    processor.reset_all_detectors()
                    await websocket.send_json({"type": "METRICS", "metrics": {"risk_level": "PAUSED", "kss": 1.0}})
                    continue

                if frame_bgr is not None:
                    annotated_frame, metrics, alert = processor.process_frame(frame_bgr, extra_sensors=sensors)
                    
                    response = {
                        "type": "METRICS",
                        "metrics": metrics
                    }
                    
                    if annotated_frame is not None:
                        _, buffer = cv2.imencode('.jpg', annotated_frame)
                        response["annotated_frame"] = base64.b64encode(buffer).decode('utf-8')
                    
                    if alert:
                        # In simulation, we intercept the alert and mark if an incident/evidence *would* be created
                        alert["incident_simulated"] = True
                        alert["evidence_simulated"] = True
                        response["alert"] = alert
                        
                    await websocket.send_json(response)
                    
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error(f"Simulation error: {e}")
                
    except WebSocketDisconnect:
        logger.info("Simulation WS disconnected")
