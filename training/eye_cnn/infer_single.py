"""
Classify a single eye/face image as AWAKE or SLEEPY.

Supports both the PyTorch model (.pt) and the ONNX model (.onnx).
Prefers ONNX when available (faster cold-start, no torch overhead in prod).

Usage
-----
    # PyTorch
    python -m training.eye_cnn.infer_single path/to/eye.png

    # ONNX
    python -m training.eye_cnn.infer_single path/to/eye.png --backend onnx

    # Explicit model path
    python -m training.eye_cnn.infer_single path/to/eye.png \\
        --model-path models/eye_cnn/eye_sleepiness.pt

Output
------
    Label       : SLEEPY
    Confidence  : 0.9142
    P(AWAKE)    : 0.0858
    P(SLEEPY)   : 0.9142
"""

import argparse
import os
import sys

import cv2
import numpy as np

from training.eye_cnn import CLASS_NAMES, IDX_TO_CLASS
from training.eye_cnn.preprocessing import preprocess_eye_image


def infer_pytorch(image: np.ndarray, model_path: str) -> dict:
    """Run inference with the PyTorch model.

    Returns
    -------
    dict with keys: label, confidence, p_awake, p_sleepy
    """
    import torch
    from training.eye_cnn.model import SleepinessCNN

    model = SleepinessCNN()
    model.load_state_dict(
        torch.load(model_path, map_location="cpu", weights_only=True)
    )
    model.eval()

    tensor = preprocess_eye_image(image)              # (1, 1, 32, 32)
    with torch.no_grad():
        logits = model(tensor)                        # (1, 2)
        probs = torch.softmax(logits, dim=1).squeeze()  # (2,)

    pred_idx = int(probs.argmax())
    return {
        "label": IDX_TO_CLASS[pred_idx].upper(),
        "confidence": float(probs[pred_idx]),
        "p_awake": float(probs[0]),
        "p_sleepy": float(probs[1]),
    }


def infer_onnx(image: np.ndarray, onnx_path: str) -> dict:
    """Run inference with the ONNX model via onnxruntime.

    Returns
    -------
    dict with keys: label, confidence, p_awake, p_sleepy
    """
    import onnxruntime as ort

    sess = ort.InferenceSession(onnx_path)
    tensor = preprocess_eye_image(image).numpy()       # (1, 1, 32, 32)
    logits = sess.run(None, {"eye_image": tensor})[0]  # (1, 2)

    # Softmax
    exp = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = (exp / exp.sum(axis=1, keepdims=True)).squeeze()

    pred_idx = int(probs.argmax())
    return {
        "label": IDX_TO_CLASS[pred_idx].upper(),
        "confidence": float(probs[pred_idx]),
        "p_awake": float(probs[0]),
        "p_sleepy": float(probs[1]),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Classify a single eye/face image (AWAKE / SLEEPY)."
    )
    parser.add_argument("image", help="Path to the eye image.")
    parser.add_argument(
        "--model-path", default=None,
        help="Path to .pt or .onnx model file (auto-detected by extension).",
    )
    parser.add_argument(
        "--backend", choices=["pytorch", "onnx"], default=None,
        help="Force backend. Auto-detected from --model-path extension.",
    )
    args = parser.parse_args()

    # ── Load image ────────────────────────────────────────────────────
    if not os.path.isfile(args.image):
        print(f"ERROR: Image file not found: {args.image}")
        sys.exit(1)

    image = cv2.imread(args.image)
    if image is None:
        print(f"ERROR: Could not read image: {args.image}")
        sys.exit(1)

    # ── Resolve model path and backend ────────────────────────────────
    pt_default = os.path.join("models", "eye_cnn", "eye_sleepiness.pt")
    onnx_default = os.path.join("models", "eye_cnn", "eye_sleepiness.onnx")
    output_pt = os.path.join("training", "eye_cnn", "output",
                             "eye_sleepiness.pt")

    if args.model_path:
        model_path = args.model_path
    elif args.backend == "onnx" and os.path.isfile(onnx_default):
        model_path = onnx_default
    elif os.path.isfile(onnx_default):
        model_path = onnx_default
        args.backend = "onnx"
    elif os.path.isfile(pt_default):
        model_path = pt_default
    elif os.path.isfile(output_pt):
        model_path = output_pt
    else:
        print("ERROR: No trained model found. Searched:")
        print(f"  {onnx_default}")
        print(f"  {pt_default}")
        print(f"  {output_pt}")
        sys.exit(1)

    if args.backend is None:
        args.backend = "onnx" if model_path.endswith(".onnx") else "pytorch"

    if not os.path.isfile(model_path):
        print(f"ERROR: Model file not found: {model_path}")
        sys.exit(1)

    # ── Inference ─────────────────────────────────────────────────────
    if args.backend == "onnx":
        result = infer_onnx(image, model_path)
    else:
        result = infer_pytorch(image, model_path)

    # ── Output ────────────────────────────────────────────────────────
    print(f"Label       : {result['label']}")
    print(f"Confidence  : {result['confidence']:.4f}")
    print(f"P(AWAKE)    : {result['p_awake']:.4f}")
    print(f"P(SLEEPY)   : {result['p_sleepy']:.4f}")
    print(f"Backend     : {args.backend}")
    print(f"Model       : {model_path}")


if __name__ == "__main__":
    main()
