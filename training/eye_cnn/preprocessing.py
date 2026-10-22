"""
Preprocessing transforms and PyTorch Dataset for sleepiness classification.

All transforms operate on **numpy ndarrays** (loaded via OpenCV) so the
exact same pipeline can be reused during real-time inference without adding
torchvision as a dependency.

Normalisation convention
------------------------
    pixel → [0, 1]  →  (x − 0.5) / 0.5  →  [−1, 1]

This is deterministic and invertible, making it safe for ONNX export.
"""

import os
import random
from typing import List, Optional, Tuple

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from training.eye_cnn import (
    CLASS_NAMES,
    INPUT_CHANNELS,
    INPUT_SIZE,
)

# ---------------------------------------------------------------------------
# Normalisation constants (used during training AND inference)
# ---------------------------------------------------------------------------
PIXEL_MEAN = 0.5
PIXEL_STD = 0.5


# ===================================================================
# Transform callables  (operate on numpy HxW uint8 arrays)
# ===================================================================

class Resize:
    """Resize to (size, size) using area interpolation."""

    def __init__(self, size: int = INPUT_SIZE):
        self.size = size

    def __call__(self, img: np.ndarray) -> np.ndarray:
        return cv2.resize(img, (self.size, self.size),
                          interpolation=cv2.INTER_AREA)


class RandomHorizontalFlip:
    """Flip left ↔ right with probability *p*.

    Safe for sleepiness classification: a horizontally-flipped awake face
    is still awake.
    """

    def __init__(self, p: float = 0.5):
        self.p = p

    def __call__(self, img: np.ndarray) -> np.ndarray:
        if random.random() < self.p:
            return cv2.flip(img, 1)
        return img


class RandomRotation:
    """Small random rotation (±degrees). Preserves sleepiness label."""

    def __init__(self, degrees: float = 10.0):
        self.degrees = degrees

    def __call__(self, img: np.ndarray) -> np.ndarray:
        angle = random.uniform(-self.degrees, self.degrees)
        h, w = img.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        return cv2.warpAffine(img, M, (w, h),
                              borderMode=cv2.BORDER_REFLECT_101)


class RandomBrightnessContrast:
    """Small brightness / contrast jitter. Does not change sleepiness label."""

    def __init__(self, brightness: float = 0.15, contrast: float = 0.15):
        self.brightness = brightness
        self.contrast = contrast

    def __call__(self, img: np.ndarray) -> np.ndarray:
        alpha = 1.0 + random.uniform(-self.contrast, self.contrast)
        beta = random.uniform(-self.brightness, self.brightness) * 255
        return cv2.convertScaleAbs(img, alpha=alpha, beta=beta)


class ToTensor:
    """HxW uint8 numpy → 1×H×W float32 torch tensor in [0, 1]."""

    def __call__(self, img: np.ndarray) -> torch.Tensor:
        t = torch.from_numpy(img).float().div(255.0)
        if t.ndim == 2:
            t = t.unsqueeze(0)          # add channel dim
        return t


class Normalize:
    """Channel-wise (x − mean) / std."""

    def __init__(self, mean: float = PIXEL_MEAN, std: float = PIXEL_STD):
        self.mean = mean
        self.std = std

    def __call__(self, tensor: torch.Tensor) -> torch.Tensor:
        return (tensor - self.mean) / self.std


class Compose:
    """Chain a list of transforms sequentially."""

    def __init__(self, transforms: list):
        self.transforms = transforms

    def __call__(self, img):
        for t in self.transforms:
            img = t(img)
        return img


# ===================================================================
# Pre-built transform pipelines
# ===================================================================

def get_train_transforms() -> Compose:
    """Transforms for the **training** split (with augmentation)."""
    return Compose([
        Resize(INPUT_SIZE),
        RandomHorizontalFlip(p=0.5),
        RandomRotation(degrees=8),
        RandomBrightnessContrast(brightness=0.15, contrast=0.15),
        ToTensor(),
        Normalize(),
    ])


def get_eval_transforms() -> Compose:
    """Transforms for **validation / test / inference** (no augmentation)."""
    return Compose([
        Resize(INPUT_SIZE),
        ToTensor(),
        Normalize(),
    ])


# ===================================================================
# Standalone preprocessing function (for single-image inference)
# ===================================================================

def preprocess_eye_image(image: np.ndarray) -> torch.Tensor:
    """Preprocess a single eye/face crop for CNN inference.

    Parameters
    ----------
    image : np.ndarray
        Eye crop in BGR or grayscale (any resolution).

    Returns
    -------
    torch.Tensor  (1, 1, 32, 32)   — batched, normalised tensor.
    """
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    transform = get_eval_transforms()
    tensor = transform(image)           # (1, 32, 32)
    return tensor.unsqueeze(0)          # (1, 1, 32, 32)


# ===================================================================
# PyTorch Dataset
# ===================================================================

class EyeDataset(Dataset):
    """Image-folder-style dataset for sleepiness classification.

    Expected directory layout::

        root/
            awake/
                img_001.png
                ...
            sleepy/
                img_001.png
                ...

    Labels are assigned based on CLASS_NAMES ordering:
        awake  → 0
        sleepy → 1
    """

    def __init__(self, root_dir: str, transform: Optional[Compose] = None):
        self.root_dir = root_dir
        self.transform = transform
        self.samples: List[Tuple[str, int]] = []
        self.class_counts = {name: 0 for name in CLASS_NAMES}

        for label, class_name in enumerate(CLASS_NAMES):
            class_dir = os.path.join(root_dir, class_name)
            if not os.path.isdir(class_dir):
                continue
            for fname in sorted(os.listdir(class_dir)):
                if fname.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                    self.samples.append(
                        (os.path.join(class_dir, fname), label)
                    )
                    self.class_counts[class_name] += 1

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        path, label = self.samples[idx]
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError(f"Failed to load image: {path}")
        if self.transform is not None:
            img = self.transform(img)
        return img, label

    def summary(self) -> str:
        """Human-readable one-liner for logging."""
        parts = [f"{name}={self.class_counts[name]}" for name in CLASS_NAMES]
        return f"EyeDataset({self.root_dir}): total={len(self)}, {', '.join(parts)}"
