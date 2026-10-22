# Sleepiness Classification CNN Training Pipeline

Lightweight convolutional neural network for binary sleepiness classification
(**AWAKE** vs **SLEEPY**), trained on the MRL Eye Dataset (forked version with
awake/sleepy labels).

> **This CNN is completely optional.**  If model weights are absent the
> existing EAR / MAR / PERCLOS drowsiness pipeline continues to work
> unchanged.

---

## CNN Architecture

```
SleepinessCNN
├── Conv2d(1→16, 3×3, pad=1) + BN + ReLU + MaxPool(2)   →  16×16×16
├── Conv2d(16→32, 3×3, pad=1) + BN + ReLU + MaxPool(2)   →  32× 8× 8
├── Conv2d(32→64, 3×3, pad=1) + BN + ReLU + MaxPool(2)   →  64× 4× 4
├── AdaptiveAvgPool2d(1)                                   →  64× 1× 1
├── Flatten + Dropout(0.3)                                 →  64
└── Linear(64 → 2)                                        →   2 logits
```

| Property           | Value                              |
|--------------------|-------------------------------------|
| Input shape        | `(B, 1, 32, 32)` — grayscale       |
| Output             | 2 logits `[awake, sleepy]`          |
| Parameters         | ≈ 23,500 (< 100 KB)                |
| Class 0            | `AWAKE`                             |
| Class 1            | `SLEEPY` **(positive class)**       |
| Normalisation      | `(pixel/255 − 0.5) / 0.5`  → [−1,1]|

---

## Dataset

The dataset is a forked version of the MRL Eye Dataset with infrared eye
images categorised into **awake** and **sleepy** states.

| Split   | Awake   | Sleepy  | Total   |
|---------|---------|---------|---------|
| Train   | 25,770  | 25,167  | 50,937  |
| Val     | 8,591   | 8,389   | 16,980  |
| Test    | 8,591   | 8,390   | 16,981  |
| **Total** | **42,952** | **41,946** | **84,898** |

### Dataset location

```
data/cnn_dataset/
├── train/
│   ├── awake/
│   └── sleepy/
├── val/
│   ├── awake/
│   └── sleepy/
└── test/
    ├── awake/
    └── sleepy/
```

The dataset is **pre-split** — do not reshuffle or recreate the splits.

---

## Quick Start

### 1. Train the CNN

```bash
python -m training.eye_cnn.train_eye_cnn \
    --dataset-dir data/cnn_dataset \
    --epochs 30 \
    --batch-size 64 \
    --lr 1e-3
```

Outputs (in `training/eye_cnn/output/`):

| File                    | Contents                                |
|-------------------------|-----------------------------------------|
| `eye_sleepiness.pt`    | Best model weights (by val F1)          |
| `training_history.json` | Per-epoch metrics                       |
| `loss_curve.png`        | Training vs validation loss plot        |
| `accuracy_curve.png`    | Training vs validation accuracy plot    |

The best model is also copied to `models/eye_cnn/eye_sleepiness.pt`.

### 2. Evaluate on the test set

```bash
python -m training.eye_cnn.evaluate_eye_cnn \
    --dataset-dir data/cnn_dataset \
    --model-path  models/eye_cnn/eye_sleepiness.pt
```

Reports: accuracy, precision, recall, F1, confusion matrix.

- **Positive class:** SLEEPY (index 1)
- Precision = TP / (TP + FP) where TP = correctly predicted SLEEPY
- Recall = TP / (TP + FN) where TP = correctly predicted SLEEPY

> **Note:** Test-set accuracy is the CNN's accuracy on the held-out test split.
> It is **not** the accuracy of the full real-time Driver Monitoring System.

### 3. Export to ONNX

```bash
python -m training.eye_cnn.export_onnx \
    --model-path models/eye_cnn/eye_sleepiness.pt \
    --onnx-path  models/eye_cnn/eye_sleepiness.onnx
```

The ONNX model is verified against the PyTorch output automatically.

### 4. Classify a single eye image

```bash
# Auto-detect backend (prefers ONNX)
python -m training.eye_cnn.infer_single path/to/eye.png

# Force PyTorch backend
python -m training.eye_cnn.infer_single path/to/eye.png --backend pytorch

# Force ONNX backend
python -m training.eye_cnn.infer_single path/to/eye.png --backend onnx
```

Output:

```
Label       : SLEEPY
Confidence  : 0.9142
P(AWAKE)    : 0.0858
P(SLEEPY)   : 0.9142
Backend     : pytorch
Model       : models/eye_cnn/eye_sleepiness.pt
```

### Model output format

The inference API returns:

```python
{
    "label": "SLEEPY",       # or "AWAKE"
    "confidence": 0.9142,    # P(predicted class)
    "p_awake": 0.0858,       # P(AWAKE)
    "p_sleepy": 0.9142,      # P(SLEEPY)
}
```

The raw `p_sleepy` value is designed for future fusion with EAR/MAR/PERCLOS
signals.

---

## Where models are saved

| File                                              | Description           |
|---------------------------------------------------|-----------------------|
| `training/eye_cnn/output/eye_sleepiness.pt`      | Training output       |
| `models/eye_cnn/eye_sleepiness.pt`               | Project-wide copy     |
| `models/eye_cnn/eye_sleepiness.onnx`             | ONNX export           |

---

## Running tests

```bash
pytest tests/test_eye_cnn.py -v
```

Tests that require trained weights or the ONNX export **skip gracefully**
if those files are absent.

---

## Preprocessing pipeline (for future real-time integration)

The exact preprocessing applied during training is available as a
standalone function:

```python
from training.eye_cnn.preprocessing import preprocess_eye_image

# eye_crop: numpy array, BGR or grayscale, any resolution
tensor = preprocess_eye_image(eye_crop)   # → (1, 1, 32, 32) torch.Tensor
```

Steps:
1. Convert to grayscale (if BGR)
2. Resize to 32×32 (area interpolation)
3. Scale to [0, 1]
4. Normalise: `(x − 0.5) / 0.5`  → [−1, 1]

The same pipeline must be used when the CNN is later integrated into
`monitoring_ws.py`.

---

## Future integration (NOT done yet)

The CNN will eventually supplement the existing EAR-based drowsiness
detection in the live monitoring pipeline.  Integration will:

1. Extract eye crops from MediaPipe face landmarks in `monitoring_ws.py`.
2. Run `preprocess_eye_image()` → CNN forward pass.
3. Use `p_sleepy` alongside EAR as an additional signal in the
   fusion engine.
4. Store CNN results (`cnn_label`, `cnn_confidence`, `cnn_p_sleepy`,
   `cnn_p_awake`) in evidence metadata.

**No existing drowsiness logic, thresholds, or WebSocket behaviour has
been modified.**

---

## Class mapping

| Index | Class   | Role              |
|-------|---------|-------------------|
| 0     | AWAKE   | Negative class    |
| 1     | SLEEPY  | **Positive class**|

The positive class is SLEEPY because detecting drowsiness is the
safety-critical objective.
