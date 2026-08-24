"""
Eye Aspect Ratio (EAR) and Mouth Aspect Ratio (MAR) computation.

EAR formula (Soukupova & Cech, 2016):
    EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
where p1..p6 are the 6 eye-contour landmarks going around the eye.
EAR stays roughly constant while the eye is open and drops sharply toward 0
when the eye closes -- this is the same principle used in production DMS,
just applied to MediaPipe's landmark set instead of dlib's.

MAR follows the same geometric idea applied to the mouth contour, used to
detect yawns.
"""

import numpy as np
from .face_mesh import LEFT_EYE, RIGHT_EYE, MOUTH


def _euclidean(a, b):
    return float(np.linalg.norm(a - b))


def eye_aspect_ratio(landmarks_px: np.ndarray, eye_indices) -> float:
    p = landmarks_px[eye_indices]
    # eye_indices order: [p1(outer), p2(top1), p3(top2), p4(inner), p5(bot2), p6(bot1)]
    vertical_1 = _euclidean(p[1], p[5])
    vertical_2 = _euclidean(p[2], p[4])
    horizontal = _euclidean(p[0], p[3])
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


def mouth_aspect_ratio(landmarks_px: np.ndarray, mouth_indices=MOUTH) -> float:
    p = landmarks_px[mouth_indices]
    # p order: [right_corner, left_corner, top_outer, top_inner, bottom_outer(mid),
    #           bottom_alt, left_upper, left_lower] -- we use a stable subset
    horizontal = _euclidean(p[0], p[1])
    vertical_1 = _euclidean(p[2], p[4])
    vertical_2 = _euclidean(p[3], p[5])
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


def compute_eye_mouth_metrics(landmarks_px: np.ndarray) -> dict:
    left_ear = eye_aspect_ratio(landmarks_px, LEFT_EYE)
    right_ear = eye_aspect_ratio(landmarks_px, RIGHT_EYE)
    avg_ear = (left_ear + right_ear) / 2.0
    mar = mouth_aspect_ratio(landmarks_px)
    return {
        "left_ear": left_ear,
        "right_ear": right_ear,
        "avg_ear": avg_ear,
        "mar": mar,
    }
