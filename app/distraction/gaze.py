"""
Eye Gaze & Multimodal Visual Attention Estimator.

Calculates normalized vertical and horizontal iris position ratios from MediaPipe's
478 facial mesh landmarks, and integrates iris gaze with 3D head pose (pitch/yaw)
to reliably determine if the driver is looking at an in-cabin object (such as a mobile
phone) or keeping their eyes on the road.

Coordinate Conventions:
- In OpenCV solvePnP with an anthropometric 3D face model:
    - Pitch: Rotation around X-axis. Frontal resting posture is ~ -5° to +2°.
             Tilting head down toward lap/phone gives POSITIVE pitch (>= +6.0°).
             Tilting head up toward rearview mirror gives NEGATIVE pitch (<= -10.0°).
    - Yaw: Rotation around Y-axis. Looking right is negative, looking left is positive.
- Iris Gaze Vertical Ratio (vert_ratio):
    - ~0.46 - 0.53 = Looking straight ahead (iris centered in eye aperture).
    - >= 0.58 = Looking noticeably downward (towards phone, lap, or lower console).
    - <= 0.40 = Looking upward.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np

# Landmark indices for MediaPipe FaceMesh / FaceLandmarker (478-point topology)
LEFT_IRIS_CENTER = 468
RIGHT_IRIS_CENTER = 473

LEFT_EYE_TOP = 159
LEFT_EYE_BOTTOM = 145
LEFT_EYE_INNER = 133
LEFT_EYE_OUTER = 33

RIGHT_EYE_TOP = 386
RIGHT_EYE_BOTTOM = 374
RIGHT_EYE_INNER = 362
RIGHT_EYE_OUTER = 263


def estimate_gaze_ratios(landmarks_px: Optional[np.ndarray]) -> Dict[str, Any]:
    """
    Compute vertical and horizontal gaze ratios from iris landmarks.

    Parameters:
        landmarks_px: (N, 2) array of pixel coordinates from MediaPipe FaceLandmarker.

    Returns:
        dict with:
            valid: bool,
            vert_ratio: float (0.0=top eyelid, 0.5=center, 1.0=bottom eyelid),
            horiz_ratio: float (0.0=right, 0.5=center, 1.0=left),
            gaze_direction: str ('center', 'down', 'up', 'left', 'right'),
            is_gaze_down: bool,
    """
    if landmarks_px is None or len(landmarks_px) < 478:
        return {
            "valid": False,
            "vert_ratio": 0.50,
            "horiz_ratio": 0.50,
            "gaze_direction": "unknown",
            "is_gaze_down": False,
        }

    try:
        # Left eye vertical aperture
        l_h = landmarks_px[LEFT_EYE_BOTTOM, 1] - landmarks_px[LEFT_EYE_TOP, 1]
        l_vert = (landmarks_px[LEFT_IRIS_CENTER, 1] - landmarks_px[LEFT_EYE_TOP, 1]) / l_h if l_h > 2.0 else 0.50

        # Right eye vertical aperture
        r_h = landmarks_px[RIGHT_EYE_BOTTOM, 1] - landmarks_px[RIGHT_EYE_TOP, 1]
        r_vert = (landmarks_px[RIGHT_IRIS_CENTER, 1] - landmarks_px[RIGHT_EYE_TOP, 1]) / r_h if r_h > 2.0 else 0.50

        avg_vert = float(np.clip((l_vert + r_vert) / 2.0, 0.0, 1.0))

        # Horizontal aperture (width)
        l_w = abs(landmarks_px[LEFT_EYE_INNER, 0] - landmarks_px[LEFT_EYE_OUTER, 0])
        l_min_x = min(landmarks_px[LEFT_EYE_INNER, 0], landmarks_px[LEFT_EYE_OUTER, 0])
        l_horiz = (landmarks_px[LEFT_IRIS_CENTER, 0] - l_min_x) / l_w if l_w > 2.0 else 0.50

        r_w = abs(landmarks_px[RIGHT_EYE_INNER, 0] - landmarks_px[RIGHT_EYE_OUTER, 0])
        r_min_x = min(landmarks_px[RIGHT_EYE_INNER, 0], landmarks_px[RIGHT_EYE_OUTER, 0])
        r_horiz = (landmarks_px[RIGHT_IRIS_CENTER, 0] - r_min_x) / r_w if r_w > 2.0 else 0.50

        avg_horiz = float(np.clip((l_horiz + r_horiz) / 2.0, 0.0, 1.0))

        # Downward gaze is verified when iris drops towards the lower eyelid (>= 0.58)
        is_gaze_down = avg_vert >= 0.58

        direction = "center"
        if avg_vert >= 0.58:
            direction = "down"
        elif avg_vert <= 0.40:
            direction = "up"
        elif avg_horiz < 0.42:
            direction = "right"
        elif avg_horiz > 0.58:
            direction = "left"

        return {
            "valid": True,
            "vert_ratio": round(avg_vert, 3),
            "horiz_ratio": round(avg_horiz, 3),
            "gaze_direction": direction,
            "is_gaze_down": is_gaze_down,
        }
    except Exception:
        return {
            "valid": False,
            "vert_ratio": 0.50,
            "horiz_ratio": 0.50,
            "gaze_direction": "unknown",
            "is_gaze_down": False,
        }


def is_driver_looking_at_phone(
    head_pitch_deg: float,
    gaze_info: Dict[str, Any],
    phone_box: Optional[Tuple[int, int, int, int]] = None,
    landmarks_px: Optional[np.ndarray] = None,
    pitch_down_threshold: float = 6.0,
    gaze_down_threshold: float = 0.58,
    ear: float = 0.30,
    ear_threshold: float = 0.20,
) -> Tuple[bool, str]:
    """
    Multimodal verification of whether driver visual attention is diverted toward a phone.

    SAFETY RULE: A phone visible in frame alone MUST NEVER trigger an alert.
    Active visual distraction requires sustained physical evidence that the driver's
    gaze or head pose is directed toward the phone.

    Returns:
        (is_looking, reason_string)
    """
    # 1. Eyes must be open to differentiate from microsleep or closed-eye nodding
    if ear < ear_threshold:
        return False, "Eyes closed / microsleep"

    # 2. Check downward head pitch
    # Looking down toward phone in lap/hand: pitch >= pitch_down_threshold (e.g. +6.0 deg)
    head_pitch_down = head_pitch_deg >= pitch_down_threshold

    # 3. Check iris gaze and whether eyes are verified on the road
    has_valid_gaze = bool(gaze_info.get("valid", False)) if gaze_info else False
    vert_ratio = float(gaze_info.get("vert_ratio", 0.50)) if gaze_info else 0.50
    gaze_down = bool(gaze_info.get("is_gaze_down", False)) or (vert_ratio >= gaze_down_threshold)
    # Eyes looking straight ahead or upward at traffic/road
    gaze_attentive_to_road = has_valid_gaze and (vert_ratio < 0.50)

    # 4. Combined subtle cues (moderate pitch down AND moderate eye gaze down)
    combined_down = (head_pitch_deg >= 3.0) and (vert_ratio >= 0.55)

    # 5. Check geometric position of phone relative to face
    phone_is_lower = True
    if phone_box is not None and landmarks_px is not None and len(landmarks_px) > 1:
        nose_y = landmarks_px[1, 1]
        phone_cy = (phone_box[1] + phone_box[3]) / 2.0
        phone_is_lower = phone_cy >= (nose_y - 20)

    is_looking = False
    reason = "Eyes on road"

    if gaze_attentive_to_road:
        # Ground-truth eye gaze confirms driver's eyes are focused on the road ahead
        is_looking = False
        reason = f"Eyes on road (gaze: {vert_ratio:.2f}, pitch: {head_pitch_deg:.1f}°)"
    elif phone_is_lower:
        if has_valid_gaze:
            # When eye gaze is tracked, require downward eye gaze OR head tilt + neutral/down gaze
            if gaze_down:
                is_looking = True
                reason = f"Looking down toward phone (gaze vert {vert_ratio:.2f} >= {gaze_down_threshold:.2f})"
            elif head_pitch_down and vert_ratio >= 0.50:
                is_looking = True
                reason = f"Looking down toward phone (head pitch {head_pitch_deg:.1f}° >= {pitch_down_threshold:.1f}°, gaze {vert_ratio:.2f})"
            elif combined_down:
                is_looking = True
                reason = f"Looking down toward phone (pitch {head_pitch_deg:.1f}°, gaze {vert_ratio:.2f})"
            else:
                reason = f"Eyes on road (pitch: {head_pitch_deg:.1f}°, gaze: {vert_ratio:.2f})"
        else:
            # Eye gaze unavailable/occluded; fall back to calibrated head pitch proxy
            if head_pitch_down:
                is_looking = True
                reason = f"Looking down toward phone (head pitch {head_pitch_deg:.1f}° >= {pitch_down_threshold:.1f}°)"
            else:
                reason = f"Head upright (pitch: {head_pitch_deg:.1f}°)"
    else:
        # High mount: require eye gaze directed at phone
        if has_valid_gaze and not gaze_attentive_to_road:
            is_looking = True
            reason = f"Looking at mounted phone (gaze: {vert_ratio:.2f})"
        else:
            is_looking = False
            reason = "Eyes on road"

    return is_looking, reason

