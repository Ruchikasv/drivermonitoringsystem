"""
Maps the raw multi-modal signals onto the Karolinska Sleepiness Scale (KSS),
the 1-9 scale that Euro NCAP's 2026 protocol explicitly references for
grading drowsiness detection systems (KSS > 7 = classify as drowsy).

Two scoring paths exist:
1. `rule_based_kss()` -- a transparent, explainable weighted formula. This
   is always available (needs no training) and is what the system falls
   back to if the learned model isn't loaded. It also doubles as the label
   generator for the synthetic training data used by the LSTM.
2. The learned fusion model (see fusion_model.py) -- a temporal model that
   looks at the *trend* of these signals over the last few minutes to
   predict where the driver is heading, not just where they are right now.

KSS reference (Åkerstedt & Gillberg, 1990):
  1 = extremely alert            6 = some signs of sleepiness
  3 = alert                      7 = sleepy, but no effort to stay awake
  5 = neither alert nor sleepy   9 = very sleepy, fighting sleep
"""

from app.drowsiness import config

KSS_LABELS = {
    1: "Extremely alert", 2: "Very alert", 3: "Alert",
    4: "Rather alert", 5: "Neither alert nor sleepy",
    6: "Some signs of sleepiness", 7: "Sleepy, no effort to stay awake",
    8: "Sleepy, some effort to stay awake", 9: "Very sleepy, fighting sleep",
}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def rule_based_kss(
    perclos: float,
    blink_rate_per_min: float = 16.0,
    microsleep_count_recent: int = 0,
    yawn_rate_per_min: float = 0.0,
    head_nod_events_recent: int = 0,
    sustained_eye_closure_seconds: float = 0.0,
) -> float:
    """
    Transparent weighted composite -> KSS (1-9), explainable so it can be
    shown on the fleet dashboard ("why was this driver flagged"). Based
    purely on visual signals: eye closure, blink pattern, yawning, and head
    pose.

    Calibrated so:
    - Normal alert driver with normal blinking (PERCLOS < 0.10) scores 1.0 - 2.5 ("Alert").
    - Mild drowsiness (elevated PERCLOS > 0.18, occasional yawns) scores 4.0 - 5.5 ("Neither alert nor sleepy").
    - Moderate fatigue (sustained eye closure >= 1.5s, repeated yawns) scores 6.0 - 7.0 ("Some signs of sleepiness").
    - Severe drowsiness / microsleep (closure >= 2.5s or multiple microsleeps + high PERCLOS) scores 7.5 - 9.0 ("Very sleepy").
    """
    score = 1.0

    # 1. PERCLOS baseline (0.0 to 1.0)
    # Only add significant score if PERCLOS exceeds normal blink baseline (~10%)
    if perclos > 0.10:
        excess_perclos = min(1.0, (perclos - 0.10) / (config.PERCLOS_CRITICAL_THRESHOLD - 0.10))
        score += excess_perclos * 3.5

    # 2. Blink rate deviation (normal is ~12-20 bpm)
    blink_dev = abs(blink_rate_per_min - 16.0) / 16.0
    if blink_dev > 0.3:
        score += _clamp((blink_dev - 0.3) / 0.7, 0, 1) * 0.8

    # 3. Active sustained eye closure
    if sustained_eye_closure_seconds >= 2.5:
        score += 3.5  # Critical prolonged microsleep
    elif sustained_eye_closure_seconds >= 1.5:
        score += 2.0  # Moderate microsleep

    # 4. Recent rolling window fatigue events
    score += _clamp(microsleep_count_recent / 2.0, 0, 1) * 2.0
    score += _clamp(yawn_rate_per_min / 2.0, 0, 1) * 1.0
    score += _clamp(head_nod_events_recent / 2.0, 0, 1) * 1.5

    return round(_clamp(score, 1.0, 9.0), 2)


def kss_label(kss_score: float) -> str:
    return KSS_LABELS[int(round(_clamp(kss_score, 1, 9)))]


def is_critical(kss_score: float) -> bool:
    return kss_score >= config.KSS_CRITICAL_THRESHOLD

