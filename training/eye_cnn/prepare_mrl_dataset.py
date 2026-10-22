"""
Prepare the MRL Eye Dataset for training.

The MRL Eye Dataset (http://mrl.cs.vsb.cz/eyedataset) contains ~84,898
infrared eye images from 37 subjects.  Filenames encode metadata:

    s{subjectID}_{imageID}_{gender}_{glasses}_{eyeState}_{reflections}_{lighting}_{sensorID}.png

    eyeState:  0 = closed,  1 = open

This script performs a **subject-aware split** so that images from the same
person never appear in more than one of train / val / test.  This prevents
identity-leakage and gives a realistic estimate of generalisation to unseen
subjects.

Split ratios (by subjects, not images):
    train  ≈ 70 %
    val    ≈ 15 %
    test   ≈ 15 %

Usage
-----
    python -m training.eye_cnn.prepare_mrl_dataset \\
        --src  path/to/extracted_mrl_dataset \\
        --dst  training/eye_cnn/dataset

After running, the destination directory will look like::

    dataset/
        train/
            closed/
            open/
        val/
            closed/
            open/
        test/
            closed/
            open/
"""

import argparse
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

# ── MRL filename regex ────────────────────────────────────────────────
# Example: s0001_00042_0_0_1_0_1_01.png
#          ^^^^^ ^^^^^ ^ ^ ^ ^ ^ ^^
#          subj  imgID g gl es rf lt sensor
_MRL_PATTERN = re.compile(
    r"^s(\d+)_(\d+)_(\d)_(\d)_(\d)_(\d)_(\d)_(\d+)\.\w+$",
    re.IGNORECASE,
)

EYE_STATE_MAP = {0: "closed", 1: "open"}


def parse_mrl_filename(filename: str):
    """Return (subject_id, eye_state_str) or None if not parsable."""
    m = _MRL_PATTERN.match(filename)
    if m is None:
        return None
    subject_id = m.group(1)          # e.g. "0001"
    eye_state = int(m.group(5))      # 0 or 1
    if eye_state not in EYE_STATE_MAP:
        return None
    return subject_id, EYE_STATE_MAP[eye_state]


def discover_images(src_dir: str):
    """Recursively find images and group by (subject_id, eye_state).

    Returns
    -------
    subject_images : dict[str, list[tuple[str, str]]]
        Maps subject_id → list of (full_path, eye_state_str).
    skipped : int
        Number of files that did not match the MRL naming convention.
    """
    subject_images = defaultdict(list)
    skipped = 0
    for root, _dirs, files in os.walk(src_dir):
        for fname in files:
            if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                continue
            parsed = parse_mrl_filename(fname)
            if parsed is None:
                skipped += 1
                continue
            subject_id, eye_state = parsed
            full_path = os.path.join(root, fname)
            subject_images[subject_id].append((full_path, eye_state))
    return dict(subject_images), skipped


def split_subjects(subject_ids, train_ratio=0.70, val_ratio=0.15, seed=42):
    """Deterministically split subject IDs into train / val / test."""
    import random as _rng
    ids = sorted(subject_ids)
    _rng.seed(seed)
    _rng.shuffle(ids)
    n = len(ids)
    n_train = max(1, int(n * train_ratio))
    n_val = max(1, int(n * val_ratio))
    train_ids = set(ids[:n_train])
    val_ids = set(ids[n_train:n_train + n_val])
    test_ids = set(ids[n_train + n_val:])
    # Safety: ensure test is non-empty
    if not test_ids and val_ids:
        moved = val_ids.pop()
        test_ids.add(moved)
    return train_ids, val_ids, test_ids


def copy_images(subject_images, split_map, dst_dir, *, dry_run=False):
    """Copy images into dst_dir/{split}/{class_name}/."""
    counters = defaultdict(lambda: defaultdict(int))
    for subject_id, images in subject_images.items():
        # Determine which split this subject belongs to
        split = None
        for split_name, id_set in split_map.items():
            if subject_id in id_set:
                split = split_name
                break
        if split is None:
            continue
        for src_path, eye_state in images:
            dst_subdir = os.path.join(dst_dir, split, eye_state)
            os.makedirs(dst_subdir, exist_ok=True)
            dst_path = os.path.join(dst_subdir, os.path.basename(src_path))
            if not dry_run:
                shutil.copy2(src_path, dst_path)
            counters[split][eye_state] += 1
    return counters


def main():
    parser = argparse.ArgumentParser(
        description="Organise the MRL Eye Dataset into train/val/test splits."
    )
    parser.add_argument(
        "--src", required=True,
        help="Path to the extracted MRL Eye Dataset root directory.",
    )
    parser.add_argument(
        "--dst", default=os.path.join("training", "eye_cnn", "dataset"),
        help="Destination directory for the organised dataset "
             "(default: training/eye_cnn/dataset).",
    )
    parser.add_argument(
        "--train-ratio", type=float, default=0.70,
        help="Fraction of subjects for training (default: 0.70).",
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.15,
        help="Fraction of subjects for validation (default: 0.15).",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible splitting (default: 42).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count files without copying.",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.src):
        print(f"ERROR: Source directory does not exist: {args.src}")
        sys.exit(1)

    print(f"Scanning MRL images in: {args.src}")
    subject_images, skipped = discover_images(args.src)

    if not subject_images:
        print("ERROR: No MRL-format images found. Check the --src path and "
              "ensure filenames match s{ID}_{num}_{g}_{gl}_{es}_{r}_{l}_{s}.png")
        sys.exit(1)

    total_images = sum(len(v) for v in subject_images.values())
    print(f"Found {total_images} images across {len(subject_images)} subjects "
          f"({skipped} files skipped — unrecognised names).")

    # ── Subject-aware split ──────────────────────────────────────────
    train_ids, val_ids, test_ids = split_subjects(
        subject_images.keys(),
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        seed=args.seed,
    )
    split_map = {"train": train_ids, "val": val_ids, "test": test_ids}

    print(f"\nSubject split (seed={args.seed}):")
    print(f"  train : {len(train_ids)} subjects — {sorted(train_ids)}")
    print(f"  val   : {len(val_ids)} subjects — {sorted(val_ids)}")
    print(f"  test  : {len(test_ids)} subjects — {sorted(test_ids)}")

    # ── Copy (or count) ──────────────────────────────────────────────
    action = "Counting" if args.dry_run else "Copying"
    print(f"\n{action} images to: {args.dst}")
    counters = copy_images(subject_images, split_map, args.dst,
                           dry_run=args.dry_run)

    print("\n════════════════════════════════════════════")
    print("  Dataset summary")
    print("════════════════════════════════════════════")
    grand_total = 0
    for split in ("train", "val", "test"):
        cls_counts = counters.get(split, {})
        split_total = sum(cls_counts.values())
        grand_total += split_total
        closed = cls_counts.get("closed", 0)
        opened = cls_counts.get("open", 0)
        print(f"  {split:5s}: {split_total:>6,}  "
              f"(closed={closed:>5,}, open={opened:>5,})")
    print(f"  {'total':5s}: {grand_total:>6,}")
    print("════════════════════════════════════════════")

    if args.dry_run:
        print("\n(dry-run — no files were copied)")
    else:
        print(f"\nDone.  Dataset is ready at: {os.path.abspath(args.dst)}")


if __name__ == "__main__":
    main()
