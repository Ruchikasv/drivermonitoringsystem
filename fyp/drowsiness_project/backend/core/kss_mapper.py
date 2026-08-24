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

from . import config

KSS_LABELS = {
    1: "Extremely alert", 2: "Very alert", 3: "Alert",
    4: "Rather alert", 5: "Neither alert nor sleepy",
    6: "Some signs of sleepiness", 7: "Sleepy, no effort to stay awake",
    8: "Sleepy, some effort to stay awake", 9: "Very sleepy, fighting sleep",
}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def rule_based_kss(perclos: float, blink_rate_per_min: float,
                    microsleep_count_recent: int, yawn_rate_per_min: float,
                    head_nod_events_recent: int) -> float:
    """
    Transparent weighted composite -> KSS (1-9), explainable so it can be
    shown on the fleet dashboard ("why was this driver flagged"). Based
    purely on visual signals: eye closure, blink pattern, yawning, and head
    pose -- no physiological/heart-rate signal involved.
    """
    score = 1.0

    # PERCLOS is the strongest validated single predictor of fatigue.
    score += _clamp(perclos / config.PERCLOS_CRITICAL_THRESHOLD, 0, 1) * 4.5

    # Elevated or heavily suppressed blink rate both correlate with fatigue;
    # a normal alert blink rate is roughly 12-20/min.
    blink_dev = abs(blink_rate_per_min - 16) / 16
    score += _clamp(blink_dev, 0, 1) * 1.0

    score += _clamp(microsleep_count_recent / 3.0, 0, 1) * 1.8
    score += _clamp(yawn_rate_per_min / 3.0, 0, 1) * 1.2
    score += _clamp(head_nod_events_recent / 3.0, 0, 1) * 1.5

    return round(_clamp(score, 1.0, 9.0), 2)


def kss_label(kss_score: float) -> str:
    return KSS_LABELS[int(round(_clamp(kss_score, 1, 9)))]


def is_critical(kss_score: float) -> bool:
    return kss_score >= config.KSS_CRITICAL_THRESHOLD
