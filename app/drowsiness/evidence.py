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

import logging

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


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
    trigger_reason: Optional[str] = None,
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
        "nudge": (0, 191, 255),      # Amber/Yellow-Orange
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
    # Bottom Panel: Driver details, Vehicle, EAR, MAR, PERCLOS, Head Pose, KSS, Trigger Reason
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
    cv2.putText(
        composite, "FLEET SAFETY DMS - INCIDENT EVIDENCE", (15, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA
    )
    cv2.putText(
        composite, now_str, (composite_w - 200, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1, cv2.LINE_AA
    )
    badge_text = f" [ LEVEL {alert_level}: {tier_text} ] "
    cv2.putText(
        composite, badge_text, (composite_w // 2 - 80, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, tier_color, 2, cv2.LINE_AA
    )

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
    cv2.putText(composite, f"EAR: {ear_str} (closure)", (col2_x, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(composite, f"MAR: {mar_str} (yawn)", (col2_x, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(composite, f"PERCLOS: {perclos_str}", (col2_x, y1 + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

    # Column 3: Head Pose & Fatigue Trigger
    pitch_val = head_pose.get("pitch", 0.0) if head_pose else 0.0
    kss_str = f"{kss_score:.1f}" if kss_score is not None else "N/A"
    cv2.putText(composite, f"Pitch: {pitch_val:.1f} deg | KSS: {kss_str}/9", (col3_x, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    reason_display = (trigger_reason or "Severe drowsiness detected")[:42]
    cv2.putText(composite, f"Reason: {reason_display}", (col3_x, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.42, tier_color, 1, cv2.LINE_AA)
    cv2.putText(composite, f"Status: LEVEL {alert_level} CRITICAL", (col3_x, y1 + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, tier_color, 1, cv2.LINE_AA)

    # Save to disk
    filename = f"evidence_d{driver_id}_s{session_id}_{file_timestamp}_{event_type}.jpg"
    full_file_path = evidence_dir / filename
    write_ok = cv2.imwrite(str(full_file_path), composite, [int(cv2.IMWRITE_JPEG_QUALITY), 90])

    # Relative path from project root — MUST match EVIDENCE_DIR relative to PROJECT_ROOT
    rel_path = f"data/evidence/{filename}"

    # Post-write verification logging
    if write_ok and full_file_path.exists():
        logger.info(
            "[EVIDENCE] Screenshot written successfully."
            " abs_path=%s | rel_path=%s | size_bytes=%d",
            str(full_file_path),
            rel_path,
            full_file_path.stat().st_size,
        )
    else:
        logger.error(
            "[EVIDENCE] FAILED to write screenshot! abs_path=%s | cv2.imwrite returned %s",
            str(full_file_path),
            write_ok,
        )

    return rel_path


def generate_alcohol_lockout_evidence(
    frame_bgr: Optional[np.ndarray],
    driver_name: str,
    driver_id: int,
    vehicle_registration: Optional[str],
    session_id: int,
    analog_value: int,
    threshold_value: int,
) -> tuple[str, Optional[str]]:
    """
    Creates alcohol lockout evidence images:
    1. Warning Screenshot: A styled composite warning image with prominent lockout banner,
       analog reading, threshold, driver details, and safety status.
    2. Captured Driver/Camera Frame: The raw frame captured at the moment of the lockout (if available).

    Returns
    -------
    tuple[str, Optional[str]]
        (warning_rel_path, raw_rel_path)
    """
    evidence_dir = settings.EVIDENCE_DIR
    evidence_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = now.strftime("%Y%m%d_%H%M%S_%f")[:19]

    # 1. Save raw camera frame if present
    raw_rel_path: Optional[str] = None
    if frame_bgr is not None and getattr(frame_bgr, "size", 0) > 0:
        raw_filename = f"evidence_d{driver_id}_s{session_id}_{file_timestamp}_alcohol_raw.jpg"
        full_raw_path = evidence_dir / raw_filename
        write_raw_ok = cv2.imwrite(str(full_raw_path), frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if write_raw_ok and full_raw_path.exists():
            raw_rel_path = f"data/evidence/{raw_filename}"
            logger.info("[EVIDENCE] Alcohol raw camera frame saved: %s", raw_rel_path)

    # 2. Build Warning Screenshot composite
    if frame_bgr is not None and getattr(frame_bgr, "size", 0) > 0:
        canvas_frame = frame_bgr.copy()
        h, w = canvas_frame.shape[:2]
    else:
        h, w = 480, 640
        canvas_frame = np.zeros((h, w, 3), dtype=np.uint8)
        canvas_frame[:] = (20, 15, 25)  # Dark slate background
        cv2.putText(
            canvas_frame,
            "NO LIVE CAMERA FEED AT SENSOR EVENT",
            (w // 2 - 210, h // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (160, 160, 170),
            2,
            cv2.LINE_AA,
        )

    lockout_color = (40, 40, 230)  # Bright red (BGR)
    warning_yellow = (0, 215, 255)

    # Draw semi-transparent alert banner on the frame
    overlay = canvas_frame.copy()
    banner_y1 = max(10, h // 2 - 50)
    banner_y2 = min(h - 10, h // 2 + 50)
    cv2.rectangle(overlay, (20, banner_y1), (w - 20, banner_y2), (15, 10, 80), -1)
    cv2.rectangle(overlay, (20, banner_y1), (w - 20, banner_y2), lockout_color, 2)
    cv2.addWeighted(overlay, 0.75, canvas_frame, 0.25, 0, canvas_frame)

    cv2.putText(
        canvas_frame,
        "VEHICLE OPERATION RESTRICTED - ALCOHOL LOCKOUT",
        (35, banner_y1 + 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    subtext = f"MQ-3 Sensor: {analog_value} / 1023 (Threshold: {threshold_value}) - Ignition Interlock Active"
    cv2.putText(
        canvas_frame,
        subtext,
        (35, banner_y1 + 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        warning_yellow,
        1,
        cv2.LINE_AA,
    )

    top_bar_h = 44
    bottom_bar_h = 100
    composite_h = h + top_bar_h + bottom_bar_h
    composite_w = max(w, 640)

    composite = np.zeros((composite_h, composite_w, 3), dtype=np.uint8)
    composite[:] = (30, 20, 15)

    frame_x_offset = (composite_w - w) // 2
    composite[top_bar_h : top_bar_h + h, frame_x_offset : frame_x_offset + w] = canvas_frame

    # --- TOP BAR ---
    cv2.putText(
        composite,
        "FLEET SAFETY DMS - INCIDENT EVIDENCE",
        (15, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        composite,
        now_str,
        (composite_w - 200, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (160, 160, 160),
        1,
        cv2.LINE_AA,
    )
    badge_text = " [ LEVEL 3: ALCOHOL LOCKOUT ] "
    cv2.putText(
        composite,
        badge_text,
        (composite_w // 2 - 120, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        lockout_color,
        2,
        cv2.LINE_AA,
    )
    cv2.line(composite, (0, top_bar_h - 1), (composite_w, top_bar_h - 1), (50, 45, 40), 1)

    # --- BOTTOM PANEL ---
    panel_y = top_bar_h + h
    cv2.line(composite, (0, panel_y), (composite_w, panel_y), (50, 45, 40), 1)

    col1_x = 15
    col2_x = composite_w // 3
    col3_x = (composite_w * 2) // 3
    y1 = panel_y + 25

    # Column 1: Identity
    cv2.putText(composite, f"Driver: {driver_name} (#{driver_id})", (col1_x, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (240, 240, 240), 1, cv2.LINE_AA)
    cv2.putText(composite, f"Vehicle: {vehicle_registration or 'Unassigned'}", (col1_x, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(composite, f"Session: #{session_id}", (col1_x, y1 + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 140), 1, cv2.LINE_AA)

    # Column 2: MQ-3 Sensor Telemetry
    cv2.putText(composite, f"MQ-3 Analog: {analog_value} / 1023", (col2_x, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (240, 100, 100), 1, cv2.LINE_AA)
    cv2.putText(composite, f"Lockout Threshold: {threshold_value}", (col2_x, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(composite, "Protocol: Safety Interlock 423", (col2_x, y1 + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

    # Column 3: Safety Status
    cv2.putText(composite, "Interlock: OPERATION RESTRICTED", (col3_x, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, lockout_color, 1, cv2.LINE_AA)
    cv2.putText(composite, "Resolution: Owner Clearance Req.", (col3_x, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, warning_yellow, 1, cv2.LINE_AA)
    cv2.putText(composite, "Status: LEVEL 3 CRITICAL", (col3_x, y1 + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, lockout_color, 1, cv2.LINE_AA)

    warning_filename = f"evidence_d{driver_id}_s{session_id}_{file_timestamp}_alcohol_warning.jpg"
    full_warning_path = evidence_dir / warning_filename
    cv2.imwrite(str(full_warning_path), composite, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    warning_rel_path = f"data/evidence/{warning_filename}"
    logger.info("[EVIDENCE] Alcohol warning screenshot saved: %s", warning_rel_path)

    return warning_rel_path, raw_rel_path
