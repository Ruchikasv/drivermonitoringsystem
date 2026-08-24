"""
FusionEngine: the runtime brain of the system.

Every incoming frame updates fast per-frame trackers (PERCLOS, blinks,
microsleeps, yawns, head-nods). Every `AGGREGATION_INTERVAL` seconds those
are compressed into one feature vector and pushed into a rolling sequence
buffer. That sequence is fed to the trained FatigueLSTM to produce:

  - kss_now         : current fatigue level on the Karolinska Sleepiness Scale
  - p_critical_soon : probability of crossing the critical threshold within
                       the prediction horizon (this is the "predictive",
                       not just reactive, part of the project)

If the model weights aren't available yet (e.g. fresh clone before running
the training script), it transparently falls back to the rule-based KSS
score so the system still runs end-to-end.
"""

import os
import time
from collections import deque

import numpy as np
import torch

from . import config
from .kss_mapper import rule_based_kss, kss_label, is_critical

AGGREGATION_INTERVAL = 5.0  # seconds per feature-vector timestep, must match train_synthetic.py
SEQ_LEN = 24                 # must match train_synthetic.SEQ_LEN


class FusionEngine:
    def __init__(self):
        self._seq_buffer = deque(maxlen=SEQ_LEN)
        self._last_agg_time = time.time()

        # rolling counters reset every aggregation window
        self._blinks_window = 0
        self._microsleeps_window = 0
        self._yawns_window = 0
        self._head_nods_window = 0
        self._perclos_samples = []

        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from models.fatigue_lstm import FatigueLSTM
        except ImportError:
            import sys
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from models.fatigue_lstm import FatigueLSTM

        if os.path.exists(config.MODEL_WEIGHTS_PATH):
            model = FatigueLSTM()
            model.load_state_dict(torch.load(config.MODEL_WEIGHTS_PATH, map_location="cpu"))
            model.eval()
            self.model = model
        else:
            self.model = None  # fusion engine will use rule-based fallback only

    def register_frame_events(self, perclos: float, blink_triggered: bool,
                               microsleep_triggered: bool, yawn_triggered: bool,
                               head_nod_triggered: bool):
        self._perclos_samples.append(perclos)
        if blink_triggered:
            self._blinks_window += 1
        if microsleep_triggered:
            self._microsleeps_window += 1
        if yawn_triggered:
            self._yawns_window += 1
        if head_nod_triggered:
            self._head_nods_window += 1

    def maybe_aggregate(self, now: float = None) -> dict | None:
        """Call every frame; internally only aggregates every AGGREGATION_INTERVAL
        seconds. Returns the latest fusion output dict when an aggregation
        happens, else None."""
        now = now or time.time()
        if now - self._last_agg_time < AGGREGATION_INTERVAL:
            return None

        elapsed_min = (now - self._last_agg_time) / 60.0
        avg_perclos = float(np.mean(self._perclos_samples)) if self._perclos_samples else 0.0
        blink_rate = self._blinks_window / max(elapsed_min, 1e-6)
        yawn_rate = self._yawns_window / max(elapsed_min, 1e-6)

        rule_kss = rule_based_kss(
            perclos=avg_perclos, blink_rate_per_min=blink_rate,
            microsleep_count_recent=self._microsleeps_window,
            yawn_rate_per_min=yawn_rate,
            head_nod_events_recent=self._head_nods_window,
        )

        feature_vec = np.array([
            np.clip(avg_perclos / config.PERCLOS_CRITICAL_THRESHOLD, 0, 1),
            np.clip(blink_rate / 32.0, 0, 1),
            np.clip(self._microsleeps_window / 3.0, 0, 1),
            np.clip(yawn_rate / 3.0, 0, 1),
            np.clip(self._head_nods_window / 3.0, 0, 1),
            np.clip(rule_kss / 9.0, 0, 1) * 9.0,  # keep on comparable scale to training
        ], dtype=np.float32)

        self._seq_buffer.append(feature_vec)

        kss_now, p_critical_soon, source = rule_kss, None, "rule_based"
        if self.model is not None and len(self._seq_buffer) == SEQ_LEN:
            with torch.no_grad():
                x = torch.from_numpy(np.stack(self._seq_buffer)).unsqueeze(0)  # (1, seq, feat)
                pred_kss, pred_crit = self.model(x)
                kss_now = round(float(pred_kss.item()), 2)
                p_critical_soon = round(float(pred_crit.item()), 3)
                source = "lstm_fusion"

        result = {
            "timestamp": now,
            "kss_now": kss_now,
            "kss_label": kss_label(kss_now),
            "is_critical": is_critical(kss_now),
            "p_critical_soon": p_critical_soon,
            "prediction_horizon_seconds": config.PREDICTION_HORIZON_SECONDS,
            "score_source": source,
            "raw_signals": {
                "avg_perclos": round(avg_perclos, 3),
                "blink_rate_per_min": round(blink_rate, 1),
                "microsleeps_in_window": self._microsleeps_window,
                "yawn_rate_per_min": round(yawn_rate, 1),
                "head_nods_in_window": self._head_nods_window,
            },
        }

        # reset window counters
        self._blinks_window = 0
        self._microsleeps_window = 0
        self._yawns_window = 0
        self._head_nods_window = 0
        self._perclos_samples = []
        self._last_agg_time = now

        return result
