"""
Evidence generator for driver drowsiness incidents.

Generates a high-quality, professional composite evidence image containing:
- The actual captured camera frame
- Face bounding box and target focus markings
- Driver Name and Driver ID
- Vehicle Registration & Model
- Timestamp
- Real-time Metrics: EAR, MAR, PERCLOS, Head Pose (Pitch/Yaw/Roll)
- Drowsiness Status, KSS Score & Alert Tier Badge

Persists the image to `data/evidence/` and returns the relative path.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np

from app.config import settings


def generate_evidence_screenshot(
    frame_bgr: np.ndarray,
    driver_name: str,
    driver_id: int,
    vehicle_registration: Optional[str],
    session_id: int,
    event_type: str,
    alert_level: int,
    ear: Optional[float] = None,
    mar: Optional[float] = None,
    perclos: Optional[float] = None,
    head_pose: Optional[dict] = None,
    kss_score: Optional[float] = None,
    kss_label: Optional[str] = None,
    landmarks_px: Optional[np.ndarray] = None,
) -> str:
    """
    Creates a styled composite image and saves it to data/evidence/.

    Returns
    -------
    str
        Relative path to the evidence file from settings.PROJECT_ROOT
        (e.g., 'data/evidence/evidence_d1_s2_20260824_123045_critical.jpg').
    """
    # Ensure evidence directory exists
    evidence_dir = settings.EVIDENCE_DIR
    evidence_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = now.strftime("%Y%m%d_%H%M%S_%f")[:19]

    # Create a copy of the frame to draw on
    canvas_frame = frame_bgr.copy()
    h, w = canvas_frame.shape[:2]

    # Alert color schemes (BGR)
    tier_colors = {
        "nudge": (0, 191, 255),      # Amber/Yellow-Orange (DeepSkyBlue in BGR is (0, 191, 255))
        "warning": (0, 140, 255),    # Dark Orange
        "critical": (36, 36, 237),   # Bright Red
    }
    tier_color = tier_colors.get(event_type.lower(), (0, 0, 255))
    tier_text = event_type.upper()

    # Draw face bounding box if landmarks are provided
    if landmarks_px is not None and len(landmarks_px) > 0:
        x_min = max(0, int(np.min(landmarks_px[:, 0])) - 15)
        y_min = max(0, int(np.min(landmarks_px[:, 1])) - 25)
        x_max = min(w - 1, int(np.max(landmarks_px[:, 0])) + 15)
        y_max = min(h - 1, int(np.max(landmarks_px[:, 1])) + 20)

        # Draw box corners
        corner_len = min(25, (x_max - x_min) // 4, (y_max - y_min) // 4)
        thickness = 2

        # Bounding rectangle with semi-transparent overlay
        overlay = canvas_frame.copy()
        cv2.rectangle(overlay, (x_min, y_min), (x_max, y_max), tier_color, 1)
        cv2.addWeighted(overlay, 0.4, canvas_frame, 0.6, 0, canvas_frame)

        # Corner highlights
        # Top-left
        cv2.line(canvas_frame, (x_min, y_min), (x_min + corner_len, y_min), tier_color, thickness)
        cv2.line(canvas_frame, (x_min, y_min), (x_min, y_min + corner_len), tier_color, thickness)
        # Top-right
        cv2.line(canvas_frame, (x_max, y_min), (x_max - corner_len, y_min), tier_color, thickness)
        cv2.line(canvas_frame, (x_max, y_min), (x_max, y_min + corner_len), tier_color, thickness)
        # Bottom-left
        cv2.line(canvas_frame, (x_min, y_max), (x_min + corner_len, y_max), tier_color, thickness)
        cv2.line(canvas_frame, (x_min, y_max), (x_min, y_max - corner_len), tier_color, thickness)
        # Bottom-right
        cv2.line(canvas_frame, (x_max, y_max), (x_max - corner_len, y_max), tier_color, thickness)
        cv2.line(canvas_frame, (x_max, y_max), (x_max, y_max - corner_len), tier_color, thickness)

        # Tag above box
        tag_text = f"TARGET: DRIVER #{driver_id}"
        cv2.putText(
            canvas_frame, tag_text, (x_min, max(20, y_min - 8)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, tier_color, 1, cv2.LINE_AA
        )

    # -----------------------------------------------------------------------
    # Build styled composite image:
    # Top Bar: Alert level badge + Timestamp + Fleet Safety DMS
    # Bottom Panel: Driver details, Vehicle, EAR, MAR, PERCLOS, Head Pose, KSS
    # -----------------------------------------------------------------------
    top_bar_h = 44
    bottom_bar_h = 100
    composite_h = h + top_bar_h + bottom_bar_h
    composite_w = max(w, 640)

    composite = np.zeros((composite_h, composite_w, 3), dtype=np.uint8)
    # Background: dark slate #0f172a (BGR: 42, 23, 15)
    composite[:] = (30, 20, 15)

    # Place the video frame
    frame_x_offset = (composite_w - w) // 2
    composite[top_bar_h : top_bar_h + h, frame_x_offset : frame_x_offset + w] = canvas_frame

    # --- TOP BAR ---
    # Header line
    cv2.putText(
        composite, "FLEET SAFETY DMS - INCIDENT EVIDENCE", (15, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA
    )
    # Timestamp on right
    cv2.putText(
        composite, now_str, (composite_w - 200, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1, cv2.LINE_AA
    )
    # Alert badge in center
    badge_text = f" [ LEVEL {alert_level}: {tier_text} ] "
    cv2.putText(
        composite, badge_text, (composite_w // 2 - 80, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, tier_color, 2, cv2.LINE_AA
    )

    # Divider line under top bar
    cv2.line(composite, (0, top_bar_h - 1), (composite_w, top_bar_h - 1), (50, 45, 40), 1)

    # --- BOTTOM PANEL ---
    panel_y = top_bar_h + h
    cv2.line(composite, (0, panel_y), (composite_w, panel_y), (50, 45, 40), 1)

    col1_x = 15
    col2_x = composite_w // 3
    col3_x = (composite_w * 2) // 3

    # Column 1: Identity
    y1 = panel_y + 25
    cv2.putText(composite, f"Driver: {driver_name} (#{driver_id})", (col1_x, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (240, 240, 240), 1, cv2.LINE_AA)
    cv2.putText(composite, f"Vehicle: {vehicle_registration or 'Unassigned'}", (col1_x, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(composite, f"Session: #{session_id}", (col1_x, y1 + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 140), 1, cv2.LINE_AA)

    # Column 2: Ocular & Facial Metrics
    ear_str = f"{ear:.3f}" if ear is not None else "N/A"
    mar_str = f"{mar:.3f}" if mar is not None else "N/A"
    perclos_str = f"{perclos * 100:.1f}%" if perclos is not None else "N/A"
    cv2.putText(composite, f"EAR: {ear_str} (eye closure)", (col2_x, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(composite, f"MAR: {mar_str} (yawn)", (col2_x, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(composite, f"PERCLOS: {perclos_str}", (col2_x, y1 + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

    # Column 3: Head Pose & Fatigue Level
    pitch_val = head_pose.get("pitch", 0.0) if head_pose else 0.0
    kss_str = f"{kss_score:.1f}" if kss_score is not None else "N/A"
    status_str = kss_label or event_type.capitalize()
    cv2.putText(composite, f"Head Pitch: {pitch_val:.1f} deg", (col3_x, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(composite, f"KSS Fatigue: {kss_str} / 9.0", (col3_x, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(composite, f"Status: {status_str}", (col3_x, y1 + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.48, tier_color, 1, cv2.LINE_AA)

    # Save to disk
    filename = f"evidence_d{driver_id}_s{session_id}_{file_timestamp}_{event_type}.jpg"
    full_file_path = evidence_dir / filename
    cv2.imwrite(str(full_file_path), composite, [int(cv2.IMWRITE_JPEG_QUALITY), 90])

    # Relative path from project root
    rel_path = f"data/evidence/{filename}"
    return rel_path
