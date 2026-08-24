"""
Trains FatigueLSTM on SYNTHETIC driver sessions.

Why synthetic training data, honestly explained
-------------------------------------------------
Real labeled drowsiness video datasets (NTHU-DDD, UTA-RLDD, YawDD -- see the
project README for links) require an academic-use request/download outside
this sandboxed environment and are multi-GB video corpora, not something
that can be fetched here. To ship a genuinely *working* predictive model
inside this project rather than an empty stub, we simulate physiologically
plausible driver sessions: a KSS "ground truth" trajectory that drifts
slowly over a 20-40 minute drive (exactly how real fatigue develops), and
then generate the 6 observable signals (PERCLOS, blink rate, microsleep
rate, yawn rate, head-nod rate, rule-based KSS) as noisy, correlated
functions of that hidden trajectory -- based on the same physiological
relationships documented in real fatigue research (PERCLOS and microsleep
frequency rise sharply near KSS 7-9; blink rate changes too). This is a
purely visual/behavioral signal set -- no heart-rate/physiological signal
is used anywhere in this project.

This gives the LSTM real sequence-to-target patterns to learn (rising trend
-> predict crossing critical soon) instead of just being a rule-based
score wearing a neural network costume. For production deployment, retrain
`train()` on real labeled sessions (see README) -- the model architecture
and training loop do not need to change, only the data source.
"""

import os
import sys
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.fatigue_lstm import FatigueLSTM  # noqa: E402
from core import config  # noqa: E402

SEQ_LEN = 24          # 24 timesteps @ 5s aggregation = 2 minutes of context
STEP_SECONDS = 5.0
HORIZON_STEPS = int(config.PREDICTION_HORIZON_SECONDS / STEP_SECONDS)  # 5 min horizon
N_SESSIONS = 400
SESSION_STEPS = 240    # 240 * 5s = 20 minutes per simulated session


def _simulate_kss_trajectory(n_steps: int, rng: np.random.Generator) -> np.ndarray:
    """Slow random-walk KSS ground truth, biased to drift upward over a long
    drive (as real fatigue does) with occasional recovery (driver alertness
    bump, e.g. after a break/music)."""
    kss = np.zeros(n_steps)
    kss[0] = rng.uniform(2.0, 4.0)
    drift = rng.uniform(0.01, 0.05)  # upward fatigue drift per step
    for t in range(1, n_steps):
        noise = rng.normal(0, 0.15)
        recovery = -0.6 if rng.random() < 0.01 else 0.0  # rare alertness bump
        kss[t] = kss[t - 1] + drift + noise + recovery
        kss[t] = np.clip(kss[t], 1.0, 9.0)
    return kss


def _features_from_kss(kss_val: float, rng: np.random.Generator) -> np.ndarray:
    """Generate the 6 observable features as noisy functions of hidden KSS."""
    frac = (kss_val - 1) / 8.0  # 0..1 fatigue fraction

    perclos = np.clip(rng.normal(frac * 0.4, 0.03), 0, 1)
    blink_rate_norm = np.clip(rng.normal(0.5 + 0.4 * (frac - 0.5), 0.08), 0, 1)
    microsleep_rate = np.clip(rng.normal(max(0, (frac - 0.6)) * 2.5, 0.05), 0, 1)
    yawn_rate = np.clip(rng.normal(frac * 0.8, 0.07), 0, 1)
    head_nod_rate = np.clip(rng.normal(max(0, (frac - 0.5)) * 1.6, 0.06), 0, 1)

    # rule-based KSS recomputed from *these noisy features* (not the hidden
    # truth) so the model sees the same imperfect signal the runtime system
    # would compute, and must learn to do better via temporal context.
    rule_kss = np.clip(
        1 + perclos * 5.5 + microsleep_rate * 2.2 + yawn_rate * 1.5 +
        head_nod_rate * 1.8 + rng.normal(0, 0.3),
        1, 9,
    )

    return np.array([perclos, blink_rate_norm, microsleep_rate, yawn_rate,
                      head_nod_rate, rule_kss], dtype=np.float32)


def generate_dataset(n_sessions=N_SESSIONS, session_steps=SESSION_STEPS, seed=42):
    rng = np.random.default_rng(seed)
    X, y_kss, y_crit = [], [], []

    for _ in range(n_sessions):
        kss_traj = _simulate_kss_trajectory(session_steps, rng)
        feats = np.stack([_features_from_kss(k, rng) for k in kss_traj])

        for t in range(SEQ_LEN, session_steps - HORIZON_STEPS):
            window = feats[t - SEQ_LEN:t]
            current_kss = kss_traj[t - 1]
            future_window = kss_traj[t:t + HORIZON_STEPS]
            will_cross_critical = float(np.any(future_window >= config.KSS_CRITICAL_THRESHOLD))

            X.append(window)
            y_kss.append(current_kss)
            y_crit.append(will_cross_critical)

    return (np.array(X, dtype=np.float32), np.array(y_kss, dtype=np.float32),
            np.array(y_crit, dtype=np.float32))


class FatigueSequenceDataset(Dataset):
    def __init__(self, X, y_kss, y_crit):
        self.X = torch.from_numpy(X)
        self.y_kss = torch.from_numpy(y_kss)
        self.y_crit = torch.from_numpy(y_crit)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y_kss[idx], self.y_crit[idx]


def train(epochs=12, batch_size=64, lr=1e-3, save_path=None):
    print("Generating synthetic training sessions...")
    X, y_kss, y_crit = generate_dataset()
    print(f"Dataset: {X.shape[0]} sequences, seq_len={X.shape[1]}, features={X.shape[2]}")

    n_val = int(0.15 * len(X))
    idx = np.random.default_rng(0).permutation(len(X))
    val_idx, train_idx = idx[:n_val], idx[n_val:]

    train_ds = FatigueSequenceDataset(X[train_idx], y_kss[train_idx], y_crit[train_idx])
    val_ds = FatigueSequenceDataset(X[val_idx], y_kss[val_idx], y_crit[val_idx])
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size)

    model = FatigueLSTM()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    mse = nn.MSELoss()
    bce = nn.BCELoss()

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for xb, y_kss_b, y_crit_b in train_loader:
            opt.zero_grad()
            pred_kss, pred_crit = model(xb)
            loss = mse(pred_kss, y_kss_b) + bce(pred_crit, y_crit_b)
            loss.backward()
            opt.step()
            total_loss += loss.item() * xb.size(0)
        train_loss = total_loss / len(train_ds)

        model.eval()
        val_loss, kss_mae, crit_acc, n = 0.0, 0.0, 0.0, 0
        with torch.no_grad():
            for xb, y_kss_b, y_crit_b in val_loader:
                pred_kss, pred_crit = model(xb)
                loss = mse(pred_kss, y_kss_b) + bce(pred_crit, y_crit_b)
                val_loss += loss.item() * xb.size(0)
                kss_mae += torch.abs(pred_kss - y_kss_b).sum().item()
                crit_acc += ((pred_crit > 0.5).float() == y_crit_b).sum().item()
                n += xb.size(0)
        val_loss /= n
        kss_mae /= n
        crit_acc /= n
        print(f"Epoch {epoch:2d}/{epochs}  train_loss={train_loss:.4f}  "
              f"val_loss={val_loss:.4f}  KSS_MAE={kss_mae:.3f}  crit_acc={crit_acc:.3f}")

    save_path = save_path or config.MODEL_WEIGHTS_PATH
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save(model.state_dict(), save_path)
    print(f"\nSaved trained weights to {save_path}")
    return model


if __name__ == "__main__":
    train()
