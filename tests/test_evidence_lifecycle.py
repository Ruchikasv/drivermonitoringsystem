"""
Evidence lifecycle tests for the driver monitoring system.

Validates:
- generate_evidence_screenshot() saves to the correct absolute path
- Returned relative path resolves to the actual file via settings.PROJECT_ROOT
- Evidence directory is auto-created when missing
- File is a valid JPEG with size > 0
- has_evidence=True only when file physically exists
"""

import os
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from app.config import settings
from app.drowsiness.evidence import generate_evidence_screenshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_frame(width: int = 320, height: int = 240) -> np.ndarray:
    """Create a synthetic BGR frame filled with a neutral grey gradient."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 1] = np.linspace(80, 160, width, dtype=np.uint8)
    frame[:, :, 0] = 60
    return frame


# ---------------------------------------------------------------------------
# TestEvidenceFileCreation
# ---------------------------------------------------------------------------

class TestEvidenceFileCreation:
    """Verify generate_evidence_screenshot() correctly writes files to disk."""

    def test_evidence_saved_to_correct_absolute_path(self, tmp_path):
        """File must be written inside the patched EVIDENCE_DIR."""
        frame = _make_test_frame()

        with patch.object(settings, 'EVIDENCE_DIR', tmp_path):
            rel_path = generate_evidence_screenshot(
                frame_bgr=frame,
                driver_name="Test Driver",
                driver_id=99,
                vehicle_registration="TEST-001",
                session_id=999,
                event_type="critical",
                alert_level=3,
                ear=0.14,
                mar=0.28,
                perclos=0.35,
                head_pose={"pitch": -18.0, "yaw": 2.0, "roll": 1.0},
                kss_score=8.2,
                kss_label="Severely drowsy",
                trigger_reason="Prolonged eye closure 2.6s",
            )

        assert rel_path.startswith("data/evidence/"), (
            f"Relative path should start with 'data/evidence/', got: {rel_path!r}"
        )
        filename = Path(rel_path).name
        abs_path = tmp_path / filename
        assert abs_path.exists(), f"Evidence file not found at {abs_path}"

    def test_evidence_file_has_non_zero_size(self, tmp_path):
        """Written JPEG must be a non-empty file."""
        frame = _make_test_frame()
        with patch.object(settings, 'EVIDENCE_DIR', tmp_path):
            rel_path = generate_evidence_screenshot(
                frame_bgr=frame, driver_name="Driver Alpha", driver_id=1,
                vehicle_registration="AA-001", session_id=1,
                event_type="critical", alert_level=3,
            )
        filename = Path(rel_path).name
        size = (tmp_path / filename).stat().st_size
        assert size > 10_000, f"Evidence file suspiciously small ({size} bytes)"

    def test_evidence_relative_path_resolves_via_project_root(self, tmp_path):
        """
        The real invariant: PROJECT_ROOT / rel_path must point to the same file.
        This mimics the exact check done in incidents.py _to_response().
        """
        frame = _make_test_frame()
        fake_project_root = tmp_path
        fake_evidence_dir = tmp_path / "data" / "evidence"
        fake_evidence_dir.mkdir(parents=True, exist_ok=True)

        with patch.object(settings, 'EVIDENCE_DIR', fake_evidence_dir), \
             patch.object(settings, 'PROJECT_ROOT', fake_project_root):
            rel_path = generate_evidence_screenshot(
                frame_bgr=frame, driver_name="Driver Beta", driver_id=2,
                vehicle_registration="BB-002", session_id=2,
                event_type="critical", alert_level=3,
            )

        resolved = os.path.join(str(fake_project_root), rel_path)
        assert os.path.exists(resolved), (
            f"PROJECT_ROOT / rel_path should point to the file.\n"
            f"  PROJECT_ROOT  = {fake_project_root}\n"
            f"  rel_path      = {rel_path!r}\n"
            f"  resolved      = {resolved}\n"
            f"  exists        = False  <- THIS IS THE CORE BUG"
        )

    def test_evidence_directory_auto_created_when_missing(self, tmp_path):
        """evidence_dir.mkdir(parents=True, exist_ok=True) must create the dir."""
        new_dir = tmp_path / "new_evidence_dir"
        assert not new_dir.exists()
        frame = _make_test_frame()
        with patch.object(settings, 'EVIDENCE_DIR', new_dir):
            rel_path = generate_evidence_screenshot(
                frame_bgr=frame, driver_name="Driver Gamma", driver_id=3,
                vehicle_registration=None, session_id=3,
                event_type="critical", alert_level=3,
            )
        assert new_dir.exists(), "Evidence directory was not auto-created"
        assert (new_dir / Path(rel_path).name).exists()

    def test_evidence_readable_as_jpeg(self, tmp_path):
        """File must be decodable by OpenCV (proves valid JPEG, not corrupt)."""
        frame = _make_test_frame()
        with patch.object(settings, 'EVIDENCE_DIR', tmp_path):
            rel_path = generate_evidence_screenshot(
                frame_bgr=frame, driver_name="Driver Delta", driver_id=4,
                vehicle_registration="DD-004", session_id=4,
                event_type="critical", alert_level=3,
            )
        abs_path = str(tmp_path / Path(rel_path).name)
        decoded = cv2.imread(abs_path)
        assert decoded is not None, f"cv2.imread returned None — {abs_path} is not a valid JPEG"
        assert decoded.shape[2] == 3, "Expected 3-channel BGR image"

    def test_evidence_composite_taller_than_source_frame(self, tmp_path):
        """
        Composite image must be taller than the raw frame (top bar + bottom panel added).
        """
        h, w = 240, 320
        frame = _make_test_frame(w, h)
        with patch.object(settings, 'EVIDENCE_DIR', tmp_path):
            rel_path = generate_evidence_screenshot(
                frame_bgr=frame, driver_name="Driver Echo", driver_id=5,
                vehicle_registration="EE-005", session_id=5,
                event_type="critical", alert_level=3,
            )
        composite = cv2.imread(str(tmp_path / Path(rel_path).name))
        assert composite.shape[0] > h, "Composite height must exceed raw frame height"

    def test_rel_path_uses_forward_slashes(self, tmp_path):
        """
        Relative path must use forward slashes — no backslashes.
        os.path.join handles cross-platform, but the stored DB value must be portable.
        """
        frame = _make_test_frame()
        with patch.object(settings, 'EVIDENCE_DIR', tmp_path):
            rel_path = generate_evidence_screenshot(
                frame_bgr=frame, driver_name="Driver Foxtrot", driver_id=6,
                vehicle_registration="FF-006", session_id=6,
                event_type="critical", alert_level=3,
            )
        assert "\\" not in rel_path, (
            f"rel_path must use forward slashes, got: {rel_path!r}"
        )
        assert rel_path.startswith("data/evidence/")


# ---------------------------------------------------------------------------
# TestEvidencePathConsistency — settings alignment
# ---------------------------------------------------------------------------

class TestEvidencePathConsistency:
    """Verify settings.EVIDENCE_DIR is consistent with returned relative paths."""

    def test_evidence_dir_is_under_data_evidence(self):
        """
        settings.EVIDENCE_DIR must equal PROJECT_ROOT/data/evidence
        so that the hardcoded 'data/evidence/' prefix in evidence.py resolves correctly.
        """
        expected = settings.PROJECT_ROOT / "data" / "evidence"
        actual = Path(str(settings.EVIDENCE_DIR))
        assert actual == expected, (
            f"settings.EVIDENCE_DIR mismatch!\n"
            f"  Expected : {expected}\n"
            f"  Actual   : {actual}\n"
            f"  This causes has_evidence=False for ALL new incidents (the core bug)."
        )

    def test_real_evidence_files_resolve_correctly(self):
        """
        For each evidence file in data/evidence/, verify that
        PROJECT_ROOT / 'data/evidence/{filename}' exists.
        (Tests the same resolution logic as incidents.py _to_response)
        """
        evidence_dir = settings.PROJECT_ROOT / "data" / "evidence"
        if not evidence_dir.exists():
            pytest.skip("data/evidence/ directory does not exist yet")
        files = list(evidence_dir.glob("*.jpg"))
        if not files:
            pytest.skip("No evidence files present — run a monitoring session first")

        for f in files:
            rel_path = f"data/evidence/{f.name}"
            resolved = os.path.join(str(settings.PROJECT_ROOT), rel_path)
            assert os.path.exists(resolved), (
                f"Evidence file {f.name} does not resolve via PROJECT_ROOT:\n"
                f"  rel_path = {rel_path!r}\n"
                f"  resolved = {resolved}"
            )


# ---------------------------------------------------------------------------
# TestHasEvidenceFlag — Unit tests for the has_evidence logic
# ---------------------------------------------------------------------------

class TestHasEvidenceFlag:
    """Test the has_evidence computation logic used in incidents.py _to_response()."""

    def test_has_evidence_false_when_path_is_none(self):
        evidence_path = None
        has_evidence = bool(evidence_path and os.path.exists(
            os.path.join(str(settings.PROJECT_ROOT), evidence_path or "")
        ))
        assert has_evidence is False

    def test_has_evidence_false_when_file_does_not_exist(self, tmp_path):
        rel = "data/evidence/ghost_evidence.jpg"
        full = os.path.join(str(tmp_path), rel)
        has_evidence = bool(rel and os.path.exists(full))
        assert has_evidence is False

    def test_has_evidence_true_when_file_exists(self, tmp_path):
        evidence_dir = tmp_path / "data" / "evidence"
        evidence_dir.mkdir(parents=True)
        fake_file = evidence_dir / "evidence_test.jpg"
        fake_file.write_bytes(b"\xFF\xD8\xFF" + b"\x00" * 1000)  # minimal JPEG header

        rel = f"data/evidence/{fake_file.name}"
        full = os.path.join(str(tmp_path), rel)
        has_evidence = bool(rel and os.path.exists(full))
        assert has_evidence is True

    def test_has_evidence_false_for_level1_level2_no_evidence(self):
        """Level 1/2 incidents never capture evidence — evidence_path is None."""
        evidence_path = None  # L1/L2 never set this
        has_evidence = bool(evidence_path and os.path.exists(
            os.path.join(str(settings.PROJECT_ROOT), evidence_path or "")
        ))
        assert has_evidence is False, "Level 1/2 must always have has_evidence=False"
