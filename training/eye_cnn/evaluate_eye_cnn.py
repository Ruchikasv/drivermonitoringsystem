"""
Evaluate a trained SleepinessCNN on the held-out test set.

Usage
-----
    python -m training.eye_cnn.evaluate_eye_cnn \\
        --dataset-dir data/cnn_dataset \\
        --model-path  models/eye_cnn/eye_sleepiness.pt

Reports:
    - test accuracy, precision, recall, F1
    - confusion matrix
    - per-class counts
    - positive class = SLEEPY (index 1)
"""

import argparse
import os
import sys

import numpy as np
import torch
from torch.utils.data import DataLoader

from training.eye_cnn import CLASS_NAMES
from training.eye_cnn.model import SleepinessCNN, count_parameters
from training.eye_cnn.preprocessing import EyeDataset, get_eval_transforms
from training.eye_cnn.train_eye_cnn import compute_confusion, metrics_from_cm


@torch.no_grad()
def run_test(model, loader, device):
    model.eval()
    all_preds, all_labels = [], []
    for images, labels in loader:
        images = images.to(device)
        logits = model(images)
        preds = logits.argmax(dim=1).cpu().numpy()
        all_preds.extend(preds)
        all_labels.extend(labels.numpy())
    return np.array(all_preds), np.array(all_labels)


def print_confusion_matrix(cm, class_names):
    """Pretty-print a confusion matrix."""
    header = "           " + "  ".join(f"{c:>8s}" for c in class_names)
    print(header)
    print("           " + "  ".join("--------" for _ in class_names))
    for i, row_name in enumerate(class_names):
        row = "  ".join(f"{cm[i, j]:>8d}" for j in range(len(class_names)))
        print(f"  {row_name:>8s}  {row}")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate SleepinessCNN (AWAKE vs SLEEPY)."
    )
    parser.add_argument("--dataset-dir",
                        default=os.path.join("data", "cnn_dataset"))
    parser.add_argument("--model-path", default=None,
                        help="Path to .pt model file. Auto-detected.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    # ── Resolve model path ───────────────────────────────────────────
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
            print("ERROR: No trained model found. Searched:")
            for p in candidates:
                print(f"  {p}")
            print("Train the model first with train_eye_cnn.py.")
            sys.exit(1)

    test_dir = os.path.join(args.dataset_dir, "test")
    if not os.path.isdir(test_dir):
        print(f"ERROR: Test directory not found: {test_dir}")
        sys.exit(1)

    if not os.path.isfile(args.model_path):
        print(f"ERROR: Model weights not found: {args.model_path}")
        print("Train the model first with train_eye_cnn.py.")
        sys.exit(1)

    # ── Device ────────────────────────────────────────────────────────
    if args.device:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ── Dataset ───────────────────────────────────────────────────────
    test_ds = EyeDataset(test_dir, transform=get_eval_transforms())
    if len(test_ds) == 0:
        print("ERROR: Empty test dataset.")
        sys.exit(1)
    print(f"{test_ds.summary()}")

    test_loader = DataLoader(test_ds, batch_size=args.batch_size,
                             shuffle=False, num_workers=args.num_workers)

    # ── Model ─────────────────────────────────────────────────────────
    model = SleepinessCNN()
    model.load_state_dict(torch.load(args.model_path, map_location=device,
                                     weights_only=True))
    model.to(device)
    print(f"Loaded model from {args.model_path} "
          f"({count_parameters(model):,} params)\n")

    # ── Inference ─────────────────────────────────────────────────────
    preds, labels = run_test(model, test_loader, device)
    cm = compute_confusion(preds, labels)
    m = metrics_from_cm(cm)

    # ── Report ────────────────────────────────────────────────────────
    print("════════════════════════════════════════════")
    print("  Test-Set Evaluation Results")
    print("  Sleepiness Classification (AWAKE vs SLEEPY)")
    print("════════════════════════════════════════════")
    print(f"  Samples    : {len(labels):,}")
    print(f"  Accuracy   : {m['accuracy']:.4f}")
    print(f"  Precision  : {m['precision']:.4f}  (positive = SLEEPY)")
    print(f"  Recall     : {m['recall']:.4f}  (positive = SLEEPY)")
    print(f"  F1 Score   : {m['f1']:.4f}")
    print()
    print("  Confusion Matrix (rows = actual, cols = predicted):")
    print(f"    Predicted →  {'AWAKE':>8s}  {'SLEEPY':>8s}")
    print(f"    {'AWAKE':>8s}     {cm[0,0]:>6d}    {cm[0,1]:>6d}")
    print(f"    {'SLEEPY':>8s}     {cm[1,0]:>6d}    {cm[1,1]:>6d}")
    print()

    # Per-class counts
    print("  Class distribution:")
    for i, name in enumerate(CLASS_NAMES):
        count = int((labels == i).sum())
        correct = int(cm[i, i])
        if count > 0:
            print(f"    {name.upper():>8s}: {count:>6,} samples, "
                  f"{correct:>6,} correct ({correct/count*100:.1f}%)")
        else:
            print(f"    {name.upper():>8s}: 0 samples")

    print()
    print("  Class mapping:")
    print("    AWAKE  → 0  (negative)")
    print("    SLEEPY → 1  (positive)")
    print("════════════════════════════════════════════")

    # ── Note about system accuracy ────────────────────────────────────
    print("\nNOTE: This is the CNN's accuracy on the held-out test set.")
    print("It is NOT the accuracy of the full real-time DMS.")
    print("The integrated system must be evaluated separately.")


if __name__ == "__main__":
    main()
