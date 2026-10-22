"""
SleepinessCNN — lightweight convolutional network for sleepiness classification.

Architecture
------------
Three conv blocks (Conv → BN → ReLU → MaxPool) followed by global average
pooling and a single linear classifier.

    Input : 1 × 32 × 32  (grayscale, normalised to [-1, 1])
    Output: 2 logits      [awake_score, sleepy_score]

Parameter count: ≈ 23.5 K (< 100 KB float32)
Designed for real-time CPU / edge inference alongside the existing EAR/MAR
pipeline.
"""

import torch
import torch.nn as nn


class SleepinessCNN(nn.Module):
    """Binary sleepiness classifier: AWAKE vs SLEEPY."""

    def __init__(self, num_classes: int = 2):
        super().__init__()
        self.features = nn.Sequential(
            # Block 1: 1×32×32 → 16×16×16
            nn.Conv2d(1, 16, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),

            # Block 2: 16×16×16 → 32×8×8
            nn.Conv2d(16, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),

            # Block 3: 32×8×8 → 64×4×4
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),        # 64×1×1
            nn.Flatten(),                   # 64
            nn.Dropout(0.3),
            nn.Linear(64, num_classes),     # 2 logits
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Parameters
        ----------
        x : Tensor  (B, 1, 32, 32)

        Returns
        -------
        logits : Tensor  (B, 2)
        """
        return self.classifier(self.features(x))


# ── Backward-compatible alias ─────────────────────────────────────────
EyeStateCNN = SleepinessCNN


def count_parameters(model: nn.Module) -> int:
    """Return total number of trainable parameters."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def build_model(num_classes: int = 2) -> SleepinessCNN:
    """Factory helper — builds and returns a SleepinessCNN."""
    return SleepinessCNN(num_classes=num_classes)
