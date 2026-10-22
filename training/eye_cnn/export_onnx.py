"""
Export the trained SleepinessCNN to ONNX format.

The exported model accepts the same input shape used during training:
    float32 tensor  (1, 1, 32, 32)   — batch=1, grayscale, 32×32
and produces:
    float32 tensor  (1, 2)           — logits [awake, sleepy]

The ONNX model can be loaded with the already-installed ``onnxruntime``
package for inference.

Usage
-----
    python -m training.eye_cnn.export_onnx \\
        --model-path  models/eye_cnn/eye_sleepiness.pt \\
        --onnx-path   models/eye_cnn/eye_sleepiness.onnx
"""

import argparse
import os
import sys

import numpy as np
import torch

from training.eye_cnn.model import SleepinessCNN, count_parameters
from training.eye_cnn import INPUT_SIZE, INPUT_CHANNELS


def export(model_path: str, onnx_path: str, opset: int = 13) -> None:
    """Load PyTorch weights and export to ONNX."""
    model = SleepinessCNN()
    model.load_state_dict(
        torch.load(model_path, map_location="cpu", weights_only=True)
    )
    model.eval()
    print(f"Loaded model from {model_path} "
          f"({count_parameters(model):,} params)")

    dummy_input = torch.randn(1, INPUT_CHANNELS, INPUT_SIZE, INPUT_SIZE)

    os.makedirs(os.path.dirname(onnx_path) or ".", exist_ok=True)

    torch.onnx.export(
        model,
        dummy_input,
        onnx_path,
        opset_version=opset,
        input_names=["eye_image"],
        output_names=["logits"],
        dynamic_axes={
            "eye_image": {0: "batch_size"},
            "logits": {0: "batch_size"},
        },
    )
    file_size_kb = os.path.getsize(onnx_path) / 1024
    print(f"ONNX model exported to: {onnx_path}  ({file_size_kb:.1f} KB)")

    # Verify with onnxruntime — compare against PyTorch output
    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(onnx_path)
        ort_out = sess.run(None, {"eye_image": dummy_input.numpy()})
        print(f"ONNX Runtime verification passed — output shape: "
              f"{ort_out[0].shape}")

        # Compare PyTorch vs ONNX outputs
        with torch.no_grad():
            pt_out = model(dummy_input).numpy()
        max_diff = float(np.abs(pt_out - ort_out[0]).max())
        print(f"Max PyTorch vs ONNX diff: {max_diff:.6e}")
        if max_diff < 1e-4:
            print("✓ PyTorch and ONNX outputs match within tolerance.")
        else:
            print(f"⚠ Outputs differ by {max_diff:.6e} — check model.")
    except ImportError:
        print("[WARN] onnxruntime not installed — skipping verification.")
    except Exception as e:
        print(f"[WARN] ONNX Runtime verification failed: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Export SleepinessCNN to ONNX."
    )
    parser.add_argument(
        "--model-path", default=None,
        help="Path to .pt model file. Auto-detected.",
    )
    parser.add_argument(
        "--onnx-path",
        default=os.path.join("models", "eye_cnn", "eye_sleepiness.onnx"),
    )
    parser.add_argument("--opset", type=int, default=13)
    args = parser.parse_args()

    # ── Resolve model path ────────────────────────────────────────────
    if args.model_path is None:
        candidates = [
            os.path.join("models", "eye_cnn", "eye_sleepiness.pt"),
            os.path.join("training", "eye_cnn", "output", "eye_sleepiness.pt"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                args.model_path = p
                break
        if args.model_path is None:
            print("ERROR: Model weights not found. Searched:")
            for p in candidates:
                print(f"  {p}")
            print("Train the model first with train_eye_cnn.py.")
            sys.exit(1)

    export(args.model_path, args.onnx_path, args.opset)


if __name__ == "__main__":
    main()
