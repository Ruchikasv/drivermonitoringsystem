"""
Tests for the SleepinessCNN training pipeline (AWAKE vs SLEEPY).

Tests that require trained model weights or ONNX exports skip gracefully
when those files are absent, so the existing test suite remains green.
"""

import os
import sys

import numpy as np
import pytest
import torch

# Ensure the project root is on sys.path so training.* is importable.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from training.eye_cnn import (
    CLASS_NAMES,
    CLASS_TO_IDX,
    IDX_TO_CLASS,
    INPUT_CHANNELS,
    INPUT_SIZE,
    NUM_CLASSES,
)
from training.eye_cnn.model import SleepinessCNN, build_model, count_parameters
from training.eye_cnn.preprocessing import (
    PIXEL_MEAN,
    PIXEL_STD,
    Compose,
    Normalize,
    Resize,
    ToTensor,
    get_eval_transforms,
    get_train_transforms,
    preprocess_eye_image,
)

# ── Paths for optional skip conditions ─────────────────────────────
_PT_MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "eye_cnn",
                              "eye_sleepiness.pt")
_PT_OUTPUT_PATH = os.path.join(
    PROJECT_ROOT, "training", "eye_cnn", "output", "eye_sleepiness.pt"
)
_ONNX_MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "eye_cnn",
                                "eye_sleepiness.onnx")


# ===================================================================
# Model construction tests
# ===================================================================

class TestModelConstruction:
    """Verify that SleepinessCNN builds correctly."""

    def test_build_model(self):
        model = build_model()
        assert isinstance(model, SleepinessCNN)

    def test_parameter_count_is_small(self):
        """CNN must be lightweight (< 100 K params)."""
        model = SleepinessCNN()
        n = count_parameters(model)
        assert n < 100_000, f"Model has {n:,} params — too large for edge"
        assert n > 1_000, f"Model has {n:,} params — suspiciously small"

    def test_output_shape(self):
        model = SleepinessCNN()
        model.eval()
        x = torch.randn(1, INPUT_CHANNELS, INPUT_SIZE, INPUT_SIZE)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (1, NUM_CLASSES)

    def test_batch_output_shape(self):
        model = SleepinessCNN()
        model.eval()
        batch_size = 8
        x = torch.randn(batch_size, INPUT_CHANNELS, INPUT_SIZE, INPUT_SIZE)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (batch_size, NUM_CLASSES)

    def test_softmax_sums_to_one(self):
        model = SleepinessCNN()
        model.eval()
        x = torch.randn(4, INPUT_CHANNELS, INPUT_SIZE, INPUT_SIZE)
        with torch.no_grad():
            logits = model(x)
            probs = torch.softmax(logits, dim=1)
        sums = probs.sum(dim=1)
        assert torch.allclose(sums, torch.ones(4), atol=1e-5)

    def test_backward_compat_alias(self):
        """EyeStateCNN alias should still work."""
        from training.eye_cnn.model import EyeStateCNN
        model = EyeStateCNN()
        assert isinstance(model, SleepinessCNN)


# ===================================================================
# Preprocessing tests
# ===================================================================

class TestPreprocessing:
    """Verify transforms produce correct shapes and types."""

    def test_eval_transforms_shape(self):
        transform = get_eval_transforms()
        img = np.random.randint(0, 255, (48, 64), dtype=np.uint8)
        tensor = transform(img)
        assert isinstance(tensor, torch.Tensor)
        assert tensor.shape == (1, INPUT_SIZE, INPUT_SIZE)

    def test_train_transforms_shape(self):
        transform = get_train_transforms()
        img = np.random.randint(0, 255, (48, 64), dtype=np.uint8)
        tensor = transform(img)
        assert isinstance(tensor, torch.Tensor)
        assert tensor.shape == (1, INPUT_SIZE, INPUT_SIZE)

    def test_preprocess_eye_image_grayscale(self):
        img = np.random.randint(0, 255, (24, 36), dtype=np.uint8)
        tensor = preprocess_eye_image(img)
        assert tensor.shape == (1, 1, INPUT_SIZE, INPUT_SIZE)

    def test_preprocess_eye_image_bgr(self):
        img = np.random.randint(0, 255, (24, 36, 3), dtype=np.uint8)
        tensor = preprocess_eye_image(img)
        assert tensor.shape == (1, 1, INPUT_SIZE, INPUT_SIZE)

    def test_normalize_range(self):
        """After Normalize(0.5, 0.5), values should be in [-1, 1]."""
        img = np.full((32, 32), 0, dtype=np.uint8)  # black
        transform = get_eval_transforms()
        tensor = transform(img)
        assert tensor.min() >= -1.0 - 1e-5
        assert tensor.max() <= 1.0 + 1e-5

    def test_resize_consistency(self):
        """Different input sizes should produce the same output size."""
        transform = get_eval_transforms()
        for h, w in [(16, 20), (64, 80), (100, 100)]:
            img = np.random.randint(0, 255, (h, w), dtype=np.uint8)
            tensor = transform(img)
            assert tensor.shape == (1, INPUT_SIZE, INPUT_SIZE), \
                f"Failed for input ({h}, {w})"

    def test_deterministic_eval_preprocessing(self):
        """Eval preprocessing must be deterministic (same input → same output)."""
        img = np.random.randint(0, 255, (40, 50), dtype=np.uint8)
        t1 = preprocess_eye_image(img)
        t2 = preprocess_eye_image(img)
        assert torch.allclose(t1, t2)


# ===================================================================
# Inference shape test
# ===================================================================

class TestInferenceShape:
    """End-to-end: preprocess → model → output."""

    def test_end_to_end_shape(self):
        model = SleepinessCNN()
        model.eval()
        img = np.random.randint(0, 255, (24, 36), dtype=np.uint8)
        tensor = preprocess_eye_image(img)
        with torch.no_grad():
            logits = model(tensor)
        assert logits.shape == (1, NUM_CLASSES)

    def test_end_to_end_bgr(self):
        model = SleepinessCNN()
        model.eval()
        img = np.random.randint(0, 255, (50, 70, 3), dtype=np.uint8)
        tensor = preprocess_eye_image(img)
        with torch.no_grad():
            logits = model(tensor)
        assert logits.shape == (1, NUM_CLASSES)

    def test_probability_output_format(self):
        """Inference should produce p_awake and p_sleepy."""
        model = SleepinessCNN()
        model.eval()
        img = np.random.randint(0, 255, (32, 32), dtype=np.uint8)
        tensor = preprocess_eye_image(img)
        with torch.no_grad():
            logits = model(tensor)
            probs = torch.softmax(logits, dim=1).squeeze()

        pred_idx = int(probs.argmax())
        result = {
            "label": IDX_TO_CLASS[pred_idx].upper(),
            "confidence": float(probs[pred_idx]),
            "p_awake": float(probs[0]),
            "p_sleepy": float(probs[1]),
        }
        assert result["label"] in ("AWAKE", "SLEEPY")
        assert 0.0 <= result["confidence"] <= 1.0
        assert abs(result["p_awake"] + result["p_sleepy"] - 1.0) < 1e-5


# ===================================================================
# Trained model loading (skip if weights missing)
# ===================================================================

class TestTrainedModel:
    """Tests that require trained weights — skip if absent."""

    def _get_model_path(self):
        for p in [_PT_MODEL_PATH, _PT_OUTPUT_PATH]:
            if os.path.isfile(p):
                return p
        return None

    def test_load_trained_weights(self):
        path = self._get_model_path()
        if path is None:
            pytest.skip("No trained model weights found — skipping.")
        model = SleepinessCNN()
        model.load_state_dict(
            torch.load(path, map_location="cpu", weights_only=True)
        )
        model.eval()
        x = torch.randn(1, INPUT_CHANNELS, INPUT_SIZE, INPUT_SIZE)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (1, NUM_CLASSES)


# ===================================================================
# ONNX inference (skip if model missing)
# ===================================================================

class TestOnnxInference:
    """Tests requiring the exported ONNX model — skip if absent."""

    def test_onnx_inference(self):
        if not os.path.isfile(_ONNX_MODEL_PATH):
            pytest.skip("ONNX model not found — skipping.")
        try:
            import onnxruntime as ort
        except ImportError:
            pytest.skip("onnxruntime not installed — skipping.")

        sess = ort.InferenceSession(_ONNX_MODEL_PATH)
        dummy = np.random.randn(
            1, INPUT_CHANNELS, INPUT_SIZE, INPUT_SIZE
        ).astype(np.float32)
        outputs = sess.run(None, {"eye_image": dummy})
        assert outputs[0].shape == (1, NUM_CLASSES)

    def test_onnx_matches_pytorch(self):
        """ONNX output should closely match PyTorch output."""
        path = None
        for p in [_PT_MODEL_PATH, _PT_OUTPUT_PATH]:
            if os.path.isfile(p):
                path = p
                break
        if path is None or not os.path.isfile(_ONNX_MODEL_PATH):
            pytest.skip("Need both .pt and .onnx models — skipping.")
        try:
            import onnxruntime as ort
        except ImportError:
            pytest.skip("onnxruntime not installed — skipping.")

        # PyTorch
        model = SleepinessCNN()
        model.load_state_dict(
            torch.load(path, map_location="cpu", weights_only=True)
        )
        model.eval()
        dummy = torch.randn(1, INPUT_CHANNELS, INPUT_SIZE, INPUT_SIZE)
        with torch.no_grad():
            pt_out = model(dummy).numpy()

        # ONNX
        sess = ort.InferenceSession(_ONNX_MODEL_PATH)
        ort_out = sess.run(None, {"eye_image": dummy.numpy()})[0]

        np.testing.assert_allclose(pt_out, ort_out, atol=1e-4)


# ===================================================================
# Class mapping consistency
# ===================================================================

class TestClassMapping:
    """Verify class mapping constants are consistent."""

    def test_names_tuple(self):
        assert CLASS_NAMES == ("awake", "sleepy")

    def test_to_idx(self):
        assert CLASS_TO_IDX["awake"] == 0
        assert CLASS_TO_IDX["sleepy"] == 1

    def test_from_idx(self):
        assert IDX_TO_CLASS[0] == "awake"
        assert IDX_TO_CLASS[1] == "sleepy"

    def test_num_classes(self):
        assert NUM_CLASSES == 2
        assert len(CLASS_NAMES) == NUM_CLASSES

    def test_positive_class_is_sleepy(self):
        """Sleepy (index 1) is the positive class for precision/recall."""
        assert CLASS_TO_IDX["sleepy"] == 1


# ===================================================================
# Dataset tests (skip if dataset absent)
# ===================================================================

class TestDatasetLoading:
    """Test the EyeDataset against the actual data if present."""

    _DATASET_DIR = os.path.join(PROJECT_ROOT, "data", "cnn_dataset")

    def test_dataset_class_dirs_exist(self):
        """Check that the expected folder structure exists."""
        train_dir = os.path.join(self._DATASET_DIR, "train")
        if not os.path.isdir(train_dir):
            pytest.skip("Dataset not found — skipping.")
        for cls in CLASS_NAMES:
            cls_dir = os.path.join(train_dir, cls)
            assert os.path.isdir(cls_dir), \
                f"Missing class directory: {cls_dir}"

    def test_dataset_loads_nonzero(self):
        """Dataset should load at least some samples."""
        from training.eye_cnn.preprocessing import EyeDataset, get_eval_transforms
        train_dir = os.path.join(self._DATASET_DIR, "train")
        if not os.path.isdir(train_dir):
            pytest.skip("Dataset not found — skipping.")
        ds = EyeDataset(train_dir, transform=get_eval_transforms())
        assert len(ds) > 0, "Train dataset is empty"

    def test_dataset_returns_correct_types(self):
        """Each sample should be (tensor, int)."""
        from training.eye_cnn.preprocessing import EyeDataset, get_eval_transforms
        train_dir = os.path.join(self._DATASET_DIR, "train")
        if not os.path.isdir(train_dir):
            pytest.skip("Dataset not found — skipping.")
        ds = EyeDataset(train_dir, transform=get_eval_transforms())
        if len(ds) == 0:
            pytest.skip("Train dataset is empty — skipping.")
        img, label = ds[0]
        assert isinstance(img, torch.Tensor)
        assert isinstance(label, int)
        assert img.shape == (1, INPUT_SIZE, INPUT_SIZE)
        assert label in (0, 1)


# ===================================================================
# Corrupt/invalid image handling
# ===================================================================

class TestCorruptImageHandling:
    """Verify graceful handling of bad inputs."""

    def test_preprocess_zeros(self):
        """All-zero image should not crash."""
        img = np.zeros((32, 32), dtype=np.uint8)
        tensor = preprocess_eye_image(img)
        assert tensor.shape == (1, 1, INPUT_SIZE, INPUT_SIZE)
        assert not torch.isnan(tensor).any()

    def test_preprocess_ones(self):
        """All-255 image should not crash."""
        img = np.full((32, 32), 255, dtype=np.uint8)
        tensor = preprocess_eye_image(img)
        assert tensor.shape == (1, 1, INPUT_SIZE, INPUT_SIZE)
        assert not torch.isnan(tensor).any()

    def test_preprocess_tiny_image(self):
        """Very small image should not crash."""
        img = np.random.randint(0, 255, (2, 2), dtype=np.uint8)
        tensor = preprocess_eye_image(img)
        assert tensor.shape == (1, 1, INPUT_SIZE, INPUT_SIZE)

    def test_preprocess_large_image(self):
        """Large image should not crash."""
        img = np.random.randint(0, 255, (1080, 1920), dtype=np.uint8)
        tensor = preprocess_eye_image(img)
        assert tensor.shape == (1, 1, INPUT_SIZE, INPUT_SIZE)


# ===================================================================
# Checkpointing tests
# ===================================================================

class TestCheckpointing:
    """Verify checkpoint creation and loading."""

    def test_checkpoint_save_and_load(self, tmpdir):
        from torch.optim import Adam
        from torch.optim.lr_scheduler import ReduceLROnPlateau
        
        model = SleepinessCNN()
        optimizer = Adam(model.parameters(), lr=1e-3)
        scheduler = ReduceLROnPlateau(optimizer)
        
        checkpoint_path = os.path.join(str(tmpdir), "checkpoint_latest.pt")
        
        # Save dummy checkpoint
        checkpoint = {
            "epoch": 5,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "best_val_acc": 0.85
        }
        torch.save(checkpoint, checkpoint_path)
        
        assert os.path.isfile(checkpoint_path)
        
        # Load it back
        new_model = SleepinessCNN()
        new_optimizer = Adam(new_model.parameters(), lr=1e-3)
        new_scheduler = ReduceLROnPlateau(new_optimizer)
        
        loaded = torch.load(checkpoint_path, weights_only=False)
        new_model.load_state_dict(loaded["model_state_dict"])
        new_optimizer.load_state_dict(loaded["optimizer_state_dict"])
        new_scheduler.load_state_dict(loaded["scheduler_state_dict"])
        
        assert loaded["epoch"] == 5
        assert loaded["best_val_acc"] == 0.85
        
        # Verify model parameters match
        for p1, p2 in zip(model.parameters(), new_model.parameters()):
            assert torch.allclose(p1, p2)

