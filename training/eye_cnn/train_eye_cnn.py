"""
Train the SleepinessCNN on a prepared sleepiness classification dataset.

Usage
-----
    python -m training.eye_cnn.train_eye_cnn \\
        --dataset-dir data/cnn_dataset \\
        --epochs 30 \\
        --batch-size 64 \\
        --lr 1e-3

Outputs (in --output-dir, default: training/eye_cnn/output):
    sleepiness_cnn_best.pt   — best model weights (by val F1)
    training_history.json    — per-epoch metrics
    loss_curve.png           — train vs val loss plot
    accuracy_curve.png       — train vs val accuracy plot
"""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

from training.eye_cnn.model import SleepinessCNN, count_parameters
from training.eye_cnn.preprocessing import (
    EyeDataset,
    get_eval_transforms,
    get_train_transforms,
)
from training.eye_cnn import CLASS_NAMES


# ===================================================================
# Metrics helpers
# ===================================================================

def compute_confusion(preds, labels, num_classes=2):
    """Compute confusion matrix from flat prediction/label arrays."""
    cm = np.zeros((num_classes, num_classes), dtype=np.int64)
    for p, t in zip(preds, labels):
        cm[t][p] += 1
    return cm


def metrics_from_cm(cm):
    """Precision, recall, F1 for the *positive* class (sleepy = 1).

    In sleepiness classification the positive class is SLEEPY (index 1)
    because detecting drowsiness is the safety-critical objective.
    """
    tp = int(cm[1, 1])   # true positives  — predicted sleepy, actually sleepy
    fp = int(cm[0, 1])   # false positives — predicted sleepy, actually awake
    fn = int(cm[1, 0])   # false negatives — predicted awake, actually sleepy
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)
    accuracy = (cm.trace()) / cm.sum() if cm.sum() > 0 else 0.0
    return {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
    }


# ===================================================================
# Training / evaluation loops
# ===================================================================

def train_one_epoch(model, loader, criterion, optimizer, device):
    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = lambda x, **kwargs: x

    model.train()
    running_loss = 0.0
    all_preds, all_labels = [], []

    pbar = tqdm(loader, desc="   Training", leave=False, 
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]")
    for images, labels in pbar:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        running_loss += loss.item() * images.size(0)
        preds = logits.argmax(dim=1).cpu().numpy()
        all_preds.extend(preds)
        all_labels.extend(labels.cpu().numpy())
        
        if hasattr(pbar, "set_postfix"):
            acc = (preds == labels.cpu().numpy()).mean()
            pbar.set_postfix(loss=f"{loss.item():.3f}", acc=f"{acc*100:.1f}%")

    avg_loss = running_loss / len(loader.dataset)
    cm = compute_confusion(all_preds, all_labels)
    m = metrics_from_cm(cm)
    return avg_loss, m


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = lambda x, **kwargs: x

    model.eval()
    running_loss = 0.0
    all_preds, all_labels = [], []

    pbar = tqdm(loader, desc="   Validation", leave=False,
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]")
    for images, labels in pbar:
        images, labels = images.to(device), labels.to(device)
        logits = model(images)
        loss = criterion(logits, labels)

        running_loss += loss.item() * images.size(0)
        preds = logits.argmax(dim=1).cpu().numpy()
        all_preds.extend(preds)
        all_labels.extend(labels.cpu().numpy())

    avg_loss = running_loss / len(loader.dataset)
    cm = compute_confusion(all_preds, all_labels)
    m = metrics_from_cm(cm)
    return avg_loss, m, cm


# ===================================================================
# Plotting (optional — degrades gracefully if matplotlib absent)
# ===================================================================

def save_plots(history, output_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib not installed — skipping plot generation.")
        return

    epochs = range(1, len(history["train_loss"]) + 1)

    # Loss curve
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(epochs, history["train_loss"], label="Train loss")
    ax.plot(epochs, history["val_loss"], label="Val loss")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Loss")
    ax.set_title("Sleepiness CNN — Training vs Validation Loss")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "loss_curve.png"), dpi=150)
    plt.close(fig)

    # Accuracy curve
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(epochs, history["train_acc"], label="Train accuracy")
    ax.plot(epochs, history["val_acc"], label="Val accuracy")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Accuracy")
    ax.set_title("Sleepiness CNN — Training vs Validation Accuracy")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "accuracy_curve.png"), dpi=150)
    plt.close(fig)

    print(f"Plots saved to {output_dir}")


# ===================================================================
# Main
# ===================================================================

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Train SleepinessCNN (AWAKE vs SLEEPY)."
    )
    parser.add_argument("--dataset-dir",
                        default=os.path.join("data", "cnn_dataset"),
                        help="Root of dataset (with train/val/test).")
    parser.add_argument("--output-dir",
                        default=os.path.join("training", "eye_cnn", "output"),
                        help="Where to save model + history + plots.")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--patience", type=int, default=7,
                        help="Early-stopping patience (epochs).")
    parser.add_argument("--num-workers", type=int, default=0,
                        help="DataLoader workers (0 is safest on Windows).")
    parser.add_argument("--device", default=None,
                        help="Force device (cpu / cuda). Auto-detected.")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from the latest checkpoint if it exists.")
    args = parser.parse_args()

    # ── Paths ─────────────────────────────────────────────────────────
    train_dir = os.path.join(args.dataset_dir, "train")
    val_dir = os.path.join(args.dataset_dir, "val")
    os.makedirs(args.output_dir, exist_ok=True)
    best_model_path = os.path.join(args.output_dir, "eye_sleepiness.pt")

    if not os.path.isdir(train_dir) or not os.path.isdir(val_dir):
        print(f"ERROR: Expected train/ and val/ inside {args.dataset_dir}")
        print("Ensure the dataset directory contains train/awake, "
              "train/sleepy, val/awake, val/sleepy subdirectories.")
        sys.exit(1)

    # ── Device ────────────────────────────────────────────────────────
    if args.device:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # ── Datasets ──────────────────────────────────────────────────────
    train_ds = EyeDataset(train_dir, transform=get_train_transforms())
    val_ds = EyeDataset(val_dir, transform=get_eval_transforms())

    if len(train_ds) == 0 or len(val_ds) == 0:
        print("ERROR: Empty dataset. Check the dataset directory.")
        sys.exit(1)

    print(f"\n{train_ds.summary()}")
    print(f"{val_ds.summary()}")

    # ── Class distribution report ─────────────────────────────────────
    print("\n═══════════════════════════════════════════")
    print("  Dataset Class Distribution")
    print("═══════════════════════════════════════════")
    for split_name, ds in [("train", train_ds), ("val", val_ds)]:
        print(f"  {split_name:5s}: {len(ds):>6,} total  "
              f"(awake={ds.class_counts.get('awake', 0):>6,}, "
              f"sleepy={ds.class_counts.get('sleepy', 0):>6,})")
    print("  Class mapping: AWAKE → 0, SLEEPY → 1")
    print("═══════════════════════════════════════════\n")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size,
                              shuffle=True, num_workers=args.num_workers,
                              pin_memory=(device.type == "cuda"))
    val_loader = DataLoader(val_ds, batch_size=args.batch_size,
                            shuffle=False, num_workers=args.num_workers,
                            pin_memory=(device.type == "cuda"))

    # ── Model ─────────────────────────────────────────────────────────
    model = SleepinessCNN().to(device)
    n_params = count_parameters(model)
    print(f"SleepinessCNN — {n_params:,} trainable parameters\n")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=3,
    )

    # ── Checkpointing Logic ───────────────────────────────────────────
    checkpoint_dir = os.path.join("models", "eye_cnn", "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    latest_checkpoint_path = os.path.join(checkpoint_dir, "checkpoint_latest.pt")
    
    start_epoch = 1
    best_val_acc = 0.0
    history = {
        "train_loss": [], "val_loss": [],
        "train_acc": [], "val_acc": [],
        "val_precision": [], "val_recall": [], "val_f1": [],
    }
    
    if args.resume and os.path.isfile(latest_checkpoint_path):
        print(f"\nResuming from checkpoint: {latest_checkpoint_path}")
        checkpoint = torch.load(latest_checkpoint_path, map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        start_epoch = checkpoint["epoch"] + 1
        best_val_acc = checkpoint.get("best_val_acc", 0.0)
        print(f"Resumed at epoch {start_epoch}, best val acc was {best_val_acc:.4f}\n")
    
    epochs_no_improve = 0

    # ── Training loop ─────────────────────────────────────────────────


    print("Starting Training...")
    for epoch in range(start_epoch, args.epochs + 1):
        print(f"\nEpoch {epoch}/{args.epochs}")
        t0 = time.time()

        train_loss, train_m = train_one_epoch(
            model, train_loader, criterion, optimizer, device)
        val_loss, val_m, val_cm = evaluate(
            model, val_loader, criterion, device)

        scheduler.step(val_loss)
        elapsed = time.time() - t0
        lr = optimizer.param_groups[0]["lr"]

        # Record history
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_m["accuracy"])
        history["val_acc"].append(val_m["accuracy"])
        history["val_precision"].append(val_m["precision"])
        history["val_recall"].append(val_m["recall"])
        history["val_f1"].append(val_m["f1"])

        # Print metrics
        print(f"   Train: loss={train_loss:.4f}, acc={train_m['accuracy']:.4f}")
        print(f"   Val  : loss={val_loss:.4f}, acc={val_m['accuracy']:.4f}")
        print(f"   LR={lr:.1e} | Time={elapsed:.1f}s")

        # Save checkpoint
        checkpoint = {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "best_val_acc": max(best_val_acc, val_m["accuracy"])
        }
        torch.save(checkpoint, latest_checkpoint_path)

        # Save best model based on validation accuracy
        if val_m["accuracy"] > best_val_acc:
            best_val_acc = val_m["accuracy"]
            torch.save(model.state_dict(), best_model_path)
            epochs_no_improve = 0
            print(f"   --> Best model saved (Val Acc = {best_val_acc:.4f})")
        else:
            epochs_no_improve += 1

        # Early stopping
        if epochs_no_improve >= args.patience:
            print(f"\nEarly stopping after {args.patience} epochs without "
                  f"accuracy improvement.")
            break

    # ── Also copy best model to models/ for project-wide access ──────
    project_model_path = os.path.join("models", "eye_cnn", "eye_sleepiness.pt")
    os.makedirs(os.path.join("models", "eye_cnn"), exist_ok=True)
    if os.path.exists(best_model_path):
        import shutil
        shutil.copy2(best_model_path, project_model_path)
        print(f"\nBest model also copied to: {project_model_path}")

    # ── Save history ──────────────────────────────────────────────────
    history_path = os.path.join(args.output_dir, "training_history.json")
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"Training history saved to: {history_path}")

    # ── Plots ─────────────────────────────────────────────────────────
    save_plots(history, args.output_dir)

    # ── Final summary ─────────────────────────────────────────────────
    print("\n════════════════════════════════════════════")
    print("  Sleepiness CNN — Training complete")
    print("════════════════════════════════════════════")
    print(f"  Best val acc      : {best_val_acc:.4f}")
    print(f"  Latest checkpoint : {latest_checkpoint_path}")
    print(f"  Best model saved  : {best_model_path}")
    print(f"  Project copy      : {project_model_path}")
    print(f"  History           : {history_path}")
    print(f"  Positive class    : SLEEPY (index 1)")
    print("════════════════════════════════════════════")


if __name__ == "__main__":
    main()
