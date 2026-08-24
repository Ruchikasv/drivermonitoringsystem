"""
Head pose (pitch/yaw/roll) estimation via OpenCV's solvePnP, using a generic
3D face model matched against 6 MediaPipe landmarks. This lets us detect the
classic "head nodding forward" drowsiness cue, which is one of the most
visible signs of a driver about to fall asleep and something pure EAR-based
systems often miss (e.g. if the eyes go out of frame as the head drops).
"""

import numpy as np
import cv2
from .face_mesh import HEAD_POSE_POINTS

# Generic 3D face model points (arbitrary units, roughly anthropometric)
_MODEL_POINTS_3D = np.array([
    (0.0, 0.0, 0.0),        # nose tip
    (0.0, -330.0, -65.0),   # chin
    (-225.0, 170.0, -135.0),  # right eye corner (subject's right)
    (225.0, 170.0, -135.0),   # left eye corner
    (-150.0, -150.0, -125.0),  # right mouth corner
    (150.0, -150.0, -125.0),   # left mouth corner
], dtype=np.float64)


def estimate_head_pose(landmarks_px: np.ndarray, frame_shape) -> dict:
    h, w = frame_shape[:2]
    image_points = np.array([
        landmarks_px[HEAD_POSE_POINTS["nose_tip"]],
        landmarks_px[HEAD_POSE_POINTS["chin"]],
        landmarks_px[HEAD_POSE_POINTS["right_eye_corner"]],
        landmarks_px[HEAD_POSE_POINTS["left_eye_corner"]],
        landmarks_px[HEAD_POSE_POINTS["right_mouth_corner"]],
        landmarks_px[HEAD_POSE_POINTS["left_mouth_corner"]],
    ], dtype=np.float64)

    focal_length = w
    center = (w / 2.0, h / 2.0)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1],
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1))  # assume no lens distortion

    success, rotation_vec, _translation_vec = cv2.solvePnP(
        _MODEL_POINTS_3D, image_points, camera_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )

    if not success:
        return {"pitch": 0.0, "yaw": 0.0, "roll": 0.0, "valid": False}

    rotation_mat, _ = cv2.Rodrigues(rotation_vec)
    pose_mat = cv2.hconcat((rotation_mat, np.zeros((3, 1))))
    _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(pose_mat)
    pitch, yaw, roll = [float(a[0]) for a in euler_angles]

    # cv2.decomposeProjectionMatrix has a well-known wraparound quirk: a
    # near-frontal face often comes back as ~180 degrees instead of ~0
    # (e.g. -177.5 instead of +2.5) because of how the rotation matrix
    # decomposition resolves ambiguous axis directions. Wrap all three
    # angles into [-90, 90] so "looking at the camera" reads near 0, which
    # is what the rest of the pipeline (HEAD_NOD_PITCH_THRESHOLD_DEG) assumes.
    pitch, yaw, roll = [_wrap_to_90(a) for a in (pitch, yaw, roll)]

    return {"pitch": pitch, "yaw": yaw, "roll": roll, "valid": True}


def _wrap_to_90(angle_deg: float) -> float:
    if angle_deg > 90:
        return angle_deg - 180
    if angle_deg < -90:
        return angle_deg + 180
    return angle_deg
