"""
Unit and integration tests for Driver Distraction Detection.

Validates:
- PhoneDetector frame preprocessing (grayscale / infrared adaptation, CLAHE contrast enhancement)
- Downward head pose / gaze proxy correlation with phone presence
- Brief glances (< 2.0s) do not trigger distraction alerts
- Prolonged phone distraction (>= 2.0s) triggers confirmed alert and beep
- Alert cooldown prevents duplicate alerts during continuous distraction
- Recovery logic when driver looks back up resets the distraction timer
- Absence of phone during downward pitch does not trigger phone distraction
- Presence of phone without looking down does not trigger distraction
- Grace period tolerance for temporary 1-frame detection dropout
- Trip lifecycle rules: pause/resume/end trip resets distraction state
- Separation of distraction alerts from drowsiness detection
- Database persistence with distraction_type and duration_seconds
"""

import time
from unittest.mock import MagicMock
import numpy as np
import pytest
import torch

from app.distraction.config import (
    DISTRACTION_MIN_DURATION_SECONDS,
    DISTRACTION_ALERT_COOLDOWN_SECONDS,
    DISTRACTION_PITCH_THRESHOLD_DEG,
    DISTRACTION_CONFIDENCE_THRESHOLD,
    DISTRACTION_MIN_CONSISTENT_FRAMES,
    DISTRACTION_GRACE_PERIOD_SECONDS,
)
from app.distraction.phone_detector import PhoneDetector
from app.distraction.distraction_detector import PhoneDistractionDetector
from app.database.connection import get_connection, init_db
from app.database.monitoring_repository import MonitoringRepository


class TestPhoneDetectorPreprocessing:
    """Test preprocessing and frame adaptation in PhoneDetector."""

    def test_detector_initialization_defaults(self):
        detector = PhoneDetector(confidence_threshold=0.45, lazy_load=True)
        assert detector.confidence_threshold == 0.45
        assert detector.device is not None

    def test_preprocess_3channel_bgr_frame(self):
        detector = PhoneDetector(lazy_load=True)
        bgr_frame = np.full((480, 640, 3), 120, dtype=np.uint8)
        tensor, (orig_h, orig_w) = detector.preprocess_frame(bgr_frame, is_infrared=False)
        assert tensor.shape == (3, 320, 320)
        assert orig_h == 480
        assert orig_w == 640

    def test_preprocess_grayscale_ir_frame(self):
        detector = PhoneDetector(lazy_load=True)
        # Synthetic 2D grayscale infrared frame
        gray_frame = np.full((480, 640), 90, dtype=np.uint8)
        tensor, (orig_h, orig_w) = detector.preprocess_frame(gray_frame, is_infrared=True)
        # Must be converted to 3-channel RGB tensor for torchvision backbone
        assert tensor.shape == (3, 320, 320)
        assert orig_h == 480
        assert orig_w == 640

    def test_preprocess_empty_frame_raises_or_handles(self):
        detector = PhoneDetector(lazy_load=True)
        empty_frame = np.zeros((0, 0, 3), dtype=np.uint8)
        with pytest.raises(Exception):
            detector.preprocess_frame(empty_frame)

    def test_detection_with_mocked_model_positive(self):
        mock_model = MagicMock()
        mock_boxes = torch.tensor([[25.0, 30.0, 75.0, 100.0]], dtype=torch.float32)
        mock_scores = torch.tensor([0.88], dtype=torch.float32)
        mock_labels = torch.tensor([77], dtype=torch.int64)  # COCO 77 = cell phone

        mock_model.return_value = [{
            "boxes": mock_boxes,
            "scores": mock_scores,
            "labels": mock_labels,
        }]

        detector = PhoneDetector(confidence_threshold=0.35, model=mock_model)
        test_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        results = detector.detect(test_frame)

        assert len(results) == 1
        assert results[0]["confidence"] >= 0.80
        assert results[0]["class_name"] == "cell phone"
        assert len(results[0]["box"]) == 4

    def test_detection_with_mocked_model_negative(self):
        mock_model = MagicMock()
        # Non-phone class (e.g. 1 = person)
        mock_boxes = torch.tensor([[10.0, 10.0, 50.0, 50.0]], dtype=torch.float32)
        mock_scores = torch.tensor([0.95], dtype=torch.float32)
        mock_labels = torch.tensor([1], dtype=torch.int64)

        mock_model.return_value = [{
            "boxes": mock_boxes,
            "scores": mock_scores,
            "labels": mock_labels,
        }]

        detector = PhoneDetector(confidence_threshold=0.35, model=mock_model)
        test_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        results = detector.detect(test_frame)

        assert len(results) == 0


class TestPhoneDistractionDetectorLogic:
    """Validate temporal tracking, threshold evaluation, cooldown, and recovery."""

    def setup_method(self):
        self.detector = PhoneDistractionDetector(
            min_duration_seconds=2.0,
            cooldown_seconds=5.0,
            pitch_threshold_deg=6.0,
            confidence_threshold=0.35,
            min_consistent_frames=3,
            grace_period_seconds=0.4,
        )

    def test_phone_visible_while_looking_straight_no_alert(self):
        """Holding/seeing a phone while looking straight ahead at road must not trigger alert."""
        t0 = 1000.0
        for i in range(30):
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=0.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            assert res["distraction_confirmed"] is False
            assert res["triggered"] is False
            assert res["distraction_active"] is False

    def test_looking_down_without_phone_no_alert(self):
        """Looking down (e.g. checking speedometer, drinking water) without phone must not trigger."""
        t0 = 1000.0
        for i in range(30):
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=False,
                phone_confidence=0.0,
                phone_box=None,
                head_pitch_deg=18.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            assert res["distraction_confirmed"] is False
            assert res["triggered"] is False
            assert res["distraction_active"] is False

    def test_brief_glance_does_not_trigger_distraction(self):
        """A brief glance of 1.0s (< 2.0s threshold) followed by looking back up must not alert."""
        t0 = 1000.0
        for i in range(10):
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.75,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            assert res["distraction_confirmed"] is False
            assert res["triggered"] is False

        # Driver looks back up at road (pitch = 0.0)
        res_recovered = self.detector.update(
            now=t0 + 1.1,
            phone_detected=True,
            phone_confidence=0.75,
            phone_box=(50, 50, 150, 200),
            head_pitch_deg=0.0,
            face_detected=True,
            ear=0.30,
            is_trip_active=True,
        )
        assert res_recovered["distraction_active"] is False
        assert res_recovered["distraction_confirmed"] is False
        assert res_recovered["triggered"] is False
        assert res_recovered["duration_seconds"] == 0.0

    def test_prolonged_phone_distraction_triggers_alert(self):
        """Looking down at phone for >= 2.0s triggers confirmed distraction alert and beep."""
        t0 = 1000.0
        triggered_frames = 0
        confirmed_at_or_after_2s = False

        for i in range(30):
            curr_time = t0 + i * 0.1
            res = self.detector.update(
                now=curr_time,
                phone_detected=True,
                phone_confidence=0.80,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )

            if res["triggered"]:
                triggered_frames += 1

            if i * 0.1 >= 2.0:
                assert res["distraction_confirmed"] is True
                confirmed_at_or_after_2s = True

        # Must have triggered exactly once on crossing 2.0s threshold
        assert triggered_frames == 1
        assert confirmed_at_or_after_2s is True

    def test_cooldown_prevents_repeated_alerts_during_continuous_distraction(self):
        """During continuous distraction, alert triggers once and respects 5.0s cooldown."""
        t0 = 1000.0
        triggered_count = 0

        # Simulate 60 frames = 6.0 seconds continuous distraction
        for i in range(60):
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.80,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=14.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            if res["triggered"]:
                triggered_count += 1

        # At t=2.0s: first trigger. Next trigger can only happen after 2.0s + 5.0s = 7.0s.
        assert triggered_count == 1

    def test_recovery_when_driver_looks_back_up(self):
        """When driver returns eyes to the road, distraction state is reset immediately."""
        t0 = 1000.0
        # Distraction active for 2.2s -> confirmed
        for i in range(23):
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.80,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
        assert res["distraction_confirmed"] is True

        # Driver looks back up (pitch = +2.0 deg)
        res_up = self.detector.update(
            now=t0 + 2.4,
            phone_detected=True,
            phone_confidence=0.80,
            phone_box=(50, 50, 150, 200),
            head_pitch_deg=2.0,
            face_detected=True,
            ear=0.30,
            is_trip_active=True,
        )
        assert res_up["distraction_active"] is False
        assert res_up["distraction_confirmed"] is False
        assert res_up["triggered"] is False
        assert res_up["duration_seconds"] == 0.0

    def test_grace_period_tolerates_temporary_detection_drop(self):
        """A transient 1-frame phone detector dropout (< 0.4s) does not prematurely cancel timer."""
        t0 = 1000.0

        # 15 frames phone detected (1.5s)
        for i in range(15):
            self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.80,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )

        # 1 frame dropout @ 1.6s (< 0.4s grace period)
        res_drop = self.detector.update(
            now=t0 + 1.6,
            phone_detected=False,
            phone_confidence=0.0,
            phone_box=None,
            head_pitch_deg=15.0,
            face_detected=True,
            ear=0.30,
            is_trip_active=True,
        )
        assert res_drop["distraction_active"] is True
        assert res_drop["duration_seconds"] > 1.5

        # Detection resumes @ 1.7s -> reaches 2.2s
        for i in range(17, 24):
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.80,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )

        assert res["distraction_confirmed"] is True

    def test_dropout_exceeding_grace_period_resets_timer(self):
        """A prolonged phone disappearance (> 0.4s grace period) resets distraction timer."""
        t0 = 1000.0

        # 12 frames phone detected (1.2s)
        for i in range(12):
            self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.80,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )

        # Phone missing for 0.6s (6 frames @ 100ms > 0.4s grace period)
        for i in range(12, 18):
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=False,
                phone_confidence=0.0,
                phone_box=None,
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )

        assert res["distraction_active"] is False
        assert res["duration_seconds"] == 0.0


class TestDistractionTripLifecycleAndIsolation:
    """Ensure distraction respects trip pause/resume/end and isolates from drowsiness."""

    def test_trip_pause_resets_distraction_state(self):
        detector = PhoneDistractionDetector(min_duration_seconds=2.0)

        # Build up 1.5s of distraction
        for i in range(15):
            detector.update(
                now=1000.0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(10, 10, 50, 50),
                head_pitch_deg=16.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )

        assert detector._distraction_start_time is not None

        # Trip paused -> update with is_trip_active=False
        res_paused = detector.update(
            now=1001.6,
            phone_detected=True,
            phone_confidence=0.85,
            phone_box=(10, 10, 50, 50),
            head_pitch_deg=16.0,
            face_detected=True,
            ear=0.30,
            is_trip_active=False,
        )
        assert res_paused["distraction_active"] is False
        assert res_paused["distraction_confirmed"] is False
        assert res_paused["duration_seconds"] == 0.0
        assert detector._distraction_start_time is None

    def test_trip_end_resets_detector(self):
        detector = PhoneDistractionDetector(min_duration_seconds=2.0)

        for i in range(25):
            detector.update(
                now=1000.0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(10, 10, 50, 50),
                head_pitch_deg=16.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )

        assert detector._is_sustained is True
        detector.reset()
        assert detector._is_sustained is False
        assert detector._distraction_start_time is None

    def test_drowsiness_separation(self):
        """Distraction state does not alter drowsiness components or vice-versa."""
        from app.drowsiness.alert_manager import AlertManager
        from app.drowsiness.kss_mapper import rule_based_kss

        alert_mgr = AlertManager()
        detector = PhoneDistractionDetector(min_duration_seconds=2.0)

        # Baseline awake driver KSS score
        kss_awake = rule_based_kss(perclos=0.05)
        assert kss_awake < 4.0

        # Trigger prolonged distraction
        for i in range(25):
            dist_res = detector.update(
                now=1000.0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(10, 10, 50, 50),
                head_pitch_deg=16.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )

        assert dist_res["distraction_confirmed"] is True

        # Drowsiness alert manager state is completely unchanged
        assert alert_mgr.in_critical_state is False
        alert = alert_mgr.evaluate({
            "face_detected": True,
            "ear": 0.30,
            "mar": 0.20,
            "perclos": 0.05,
            "head_pitch": 0.0,
            "timestamp": 1000.0,
        })
        assert alert is None


class TestDatabaseIncidentPersistence:
    """Validate database storage and retrieval of distraction incidents."""

    def test_create_and_retrieve_distraction_incident(self):
        conn = get_connection(db_path=":memory:")
        init_db(conn)

        # Create driver, vehicle, and session in memory DB
        conn.execute("INSERT INTO drivers (driver_id, name, created_at) VALUES (1, 'Test Driver', datetime('now'))")
        conn.execute("INSERT INTO vehicles (vehicle_id, registration_number, model, vehicle_type, created_at) VALUES (1, 'KA-01-AB-1234', 'Volvo FH16', 'Truck', datetime('now'))")
        conn.execute("INSERT INTO monitoring_sessions (session_id, driver_id, vehicle_id, start_time, status) VALUES (1, 1, 1, datetime('now'), 'ACTIVE')")
        conn.commit()

        repo = MonitoringRepository(conn)

        # Persist a confirmed distraction incident
        incident_id = repo.create_incident(
            session_id=1,
            driver_id=1,
            vehicle_id=1,
            event_type="distraction",
            alert_level=2,
            kss_score=4.0,
            ear=0.28,
            mar=0.22,
            perclos=0.05,
            head_pitch_deg=14.5,
            distraction_type="phone",
            duration_seconds=2.45,
        )

        assert incident_id is not None
        assert incident_id > 0

        # Fetch from repository
        fetched = repo.get_incident(incident_id)
        assert fetched is not None
        assert fetched.event_type == "distraction"
        assert fetched.distraction_type == "phone"
        assert abs(fetched.duration_seconds - 2.45) < 0.01

    def test_one_database_incident_per_continuous_event(self):
        """A continuous 12.0s distraction produces multiple audio beeps but exactly 1 DB incident."""
        conn = get_connection(db_path=":memory:")
        init_db(conn)
        conn.execute("INSERT INTO drivers (driver_id, name, created_at) VALUES (1, 'Driver One', datetime('now'))")
        conn.execute("INSERT INTO vehicles (vehicle_id, registration_number, model, vehicle_type, created_at) VALUES (1, 'KA-01-AB-1111', 'Truck', 'Truck', datetime('now'))")
        conn.execute("INSERT INTO monitoring_sessions (session_id, driver_id, vehicle_id, start_time, status) VALUES (1, 1, 1, datetime('now'), 'ACTIVE')")
        conn.commit()

        repo = MonitoringRepository(conn)
        detector = PhoneDistractionDetector(min_duration_seconds=2.0, cooldown_seconds=5.0)

        t0 = 1000.0
        beep_count = 0
        db_incident_count = 0

        # Simulate 130 frames = 13.0 seconds sustained distraction
        for i in range(130):
            now = t0 + i * 0.1
            res = detector.update(
                now=now,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            if res["triggered"]:
                beep_count += 1
            if res["is_new_incident"]:
                repo.create_incident(
                    session_id=1,
                    driver_id=1,
                    vehicle_id=1,
                    event_type="distraction",
                    alert_level=2,
                    distraction_type="phone",
                    duration_seconds=res["duration_seconds"],
                )
                db_incident_count += 1

        # In 13.0s: beeps at 2.0s, 7.0s, 12.0s (3 beeps)
        assert beep_count == 3
        # Exactly ONE DB incident recorded for the continuous episode
        assert db_incident_count == 1
        incidents = repo.get_incidents_by_session(1)
        assert len(incidents) == 1
        assert incidents[0].event_type == "distraction"
        assert incidents[0].distraction_type == "phone"

    def test_second_incident_after_recovery_and_separate_event(self):
        """Driver recovers and gets distracted a second time -> exactly 2 distinct DB incidents."""
        conn = get_connection(db_path=":memory:")
        init_db(conn)
        conn.execute("INSERT INTO drivers (driver_id, name, created_at) VALUES (1, 'Driver Two', datetime('now'))")
        conn.execute("INSERT INTO vehicles (vehicle_id, registration_number, model, vehicle_type, created_at) VALUES (1, 'KA-01-AB-2222', 'Truck', 'Truck', datetime('now'))")
        conn.execute("INSERT INTO monitoring_sessions (session_id, driver_id, vehicle_id, start_time, status) VALUES (1, 1, 1, datetime('now'), 'ACTIVE')")
        conn.commit()

        repo = MonitoringRepository(conn)
        detector = PhoneDistractionDetector(min_duration_seconds=2.0, cooldown_seconds=5.0)

        t0 = 1000.0

        # Episode 1: 25 frames (2.5s) sustained distraction
        for i in range(25):
            res = detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            if res["is_new_incident"]:
                repo.create_incident(
                    session_id=1,
                    driver_id=1,
                    vehicle_id=1,
                    event_type="distraction",
                    alert_level=2,
                    distraction_type="phone",
                    duration_seconds=res["duration_seconds"],
                )

        assert len(repo.get_incidents_by_session(1)) == 1

        # Recovery: driver looks back up at road (head pitch = 0.0) for 1.5 seconds
        for i in range(25, 40):
            res_rec = detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=0.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            assert res_rec["distraction_confirmed"] is False
            assert res_rec["triggered"] is False

        # Episode 2: driver looks back down at phone for another 2.5 seconds
        for i in range(40, 65):
            res2 = detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(50, 50, 150, 200),
                head_pitch_deg=15.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            if res2["is_new_incident"]:
                repo.create_incident(
                    session_id=1,
                    driver_id=1,
                    vehicle_id=1,
                    event_type="distraction",
                    alert_level=2,
                    distraction_type="phone",
                    duration_seconds=res2["duration_seconds"],
                )

        # Must have exactly 2 distinct incidents in the database
        incidents = repo.get_incidents_by_session(1)
        assert len(incidents) == 2
        assert all(inc.event_type == "distraction" for inc in incidents)
        assert all(inc.distraction_type == "phone" for inc in incidents)


class TestPhoneDetectionContinuousAndAPI:
    """Validate continuous detection throughout active trip and API serialization."""

    def test_phone_detection_continues_after_first_beep(self):
        """Phone bounding box, confidence, and telemetry continue updating across frames after alert."""
        detector = PhoneDistractionDetector(min_duration_seconds=2.0, cooldown_seconds=5.0)
        t0 = 1000.0

        # Frame 0 to 20: Cross 2.0s threshold and fire first beep
        for i in range(21):
            res = detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.82,
                phone_box=(10, 20, 100, 150),
                head_pitch_deg=14.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )

        assert res["distraction_confirmed"] is True
        assert res["triggered"] is True

        # Frame 21 to 40 (t=2.1s to 4.0s): Even with alert cooldown active, detection MUST NOT STOP
        for i in range(21, 41):
            box = (10 + i, 20, 100 + i, 150)
            res_after = detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=box,
                head_pitch_deg=14.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            # Continues updating status and duration
            assert res_after["phone_present"] is True
            assert res_after["distraction_confirmed"] is True
            assert res_after["duration_seconds"] > 2.0
            # Cooldown active, so not re-triggering yet
            assert res_after["cooldown_active"] is True
            assert res_after["triggered"] is False

    def test_repeated_beeps_during_sustained_distraction(self):
        """If driver continues looking down at phone, beep repeats every 5 seconds."""
        detector = PhoneDistractionDetector(min_duration_seconds=2.0, cooldown_seconds=5.0)
        t0 = 1000.0
        beep_times = []

        # Simulate 13.0s continuous distraction (130 frames at 0.1s step)
        for i in range(130):
            curr_time = t0 + i * 0.1
            res = detector.update(
                now=curr_time,
                phone_detected=True,
                phone_confidence=0.88,
                phone_box=(20, 30, 80, 120),
                head_pitch_deg=16.0,
                face_detected=True,
                ear=0.30,
                is_trip_active=True,
            )
            if res["triggered"]:
                beep_times.append(round(curr_time - t0, 1))

        # First beep at 2.0s, second beep at 7.0s (2.0s + 5.0s), third beep at 12.0s (7.0s + 5.0s)
        assert beep_times == [2.0, 7.0, 12.0]
        assert detector.total_incidents == 1

    def test_authenticated_api_returns_distraction_incidents_and_metadata(self):
        """Owner can retrieve distraction incidents with distraction_type and duration metadata via API."""
        from fastapi.testclient import TestClient
        from app.api.main import app
        from app.database.owner_repository import OwnerRepository
        from app.api.dependencies import create_access_token

        conn = get_connection(db_path=":memory:")
        init_db(conn)

        o_repo = OwnerRepository(conn)
        m_repo = MonitoringRepository(conn)

        owner_id = o_repo.create_owner("Fleet Owner", "distraction_api@test.com", "Password123!")
        token = create_access_token({"sub": str(owner_id)})
        auth_headers = {"Authorization": f"Bearer {token}"}

        conn.execute("INSERT INTO drivers (driver_id, name, owner_id, created_at) VALUES (1, 'Test Driver', ?, datetime('now'))", (owner_id,))
        conn.execute("INSERT INTO vehicles (vehicle_id, registration_number, model, vehicle_type, owner_id, created_at) VALUES (1, 'KA-01-DIST', 'Van', 'Van', ?, datetime('now'))", (owner_id,))
        conn.execute("INSERT INTO monitoring_sessions (session_id, driver_id, vehicle_id, owner_id, start_time, status) VALUES (1, 1, 1, ?, datetime('now'), 'ACTIVE')", (owner_id,))
        conn.commit()

        # Insert distraction incident
        inc_id = m_repo.create_incident(
            session_id=1,
            driver_id=1,
            vehicle_id=1,
            event_type="distraction",
            alert_level=2,
            kss_score=3.5,
            distraction_type="phone",
            duration_seconds=3.2,
            owner_id=owner_id,
        )

        app.dependency_overrides[get_connection] = lambda: conn
        try:
            client = TestClient(app)
            response = client.get("/incidents/", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()

            assert len(data) >= 1
            dist_inc = next((item for item in data if item["incident_id"] == inc_id), None)
            assert dist_inc is not None
            assert dist_inc["event_type"] == "distraction"
            assert dist_inc["distraction_type"] == "phone"
            assert abs(dist_inc["duration_seconds"] - 3.2) < 0.05
            assert dist_inc["driver_id"] == 1
            assert dist_inc["session_id"] == 1
        finally:
            app.dependency_overrides.clear()
            conn.close()

    def test_process_frame_distraction_trigger_no_unbound_local_error(self):
        """DriverSessionProcessor.process_frame must not raise UnboundLocalError when distraction triggers."""
        from app.api.monitoring_ws import DriverSessionProcessor
        from unittest.mock import patch

        processor = DriverSessionProcessor(
            session_id=99,
            driver_id=1,
            driver_name="Test Driver",
            vehicle_reg="KA-01-9999",
        )

        processor.phone_detector = MagicMock()
        processor.phone_detector.detect.return_value = [
            {"box": (50, 50, 150, 200), "confidence": 0.88, "class_name": "cell phone"}
        ]

        with patch.object(processor.face_mesh, "process") as mock_mesh, \
             patch("app.api.monitoring_ws.compute_eye_mouth_metrics") as mock_geom, \
             patch("app.api.monitoring_ws.estimate_head_pose") as mock_pose, \
             patch.object(processor.distraction_detector, "update") as mock_dist_update:

            mock_mesh.return_value = (np.zeros((468, 2), dtype=np.int32), np.zeros((468, 3), dtype=np.float32))
            mock_geom.return_value = {"avg_ear": 0.30, "left_ear": 0.30, "right_ear": 0.30, "mar": 0.20}
            mock_pose.return_value = {"valid": True, "pitch": -15.0, "yaw": 0.0, "roll": 0.0}
            mock_dist_update.return_value = {
                "distraction_active": True,
                "distraction_confirmed": True,
                "triggered": True,
                "is_new_incident": True,
                "duration_seconds": 2.2,
                "cooldown_active": False,
                "looking_down": True,
                "phone_present": True,
                "distraction_type": "phone",
            }

            fake_frame = np.full((480, 640, 3), 120, dtype=np.uint8)
            annotated, metrics, alert = processor.process_frame(fake_frame)

            assert metrics["distraction_confirmed"] is True
            assert metrics["distraction_triggered"] is True
            assert alert is not None
            assert alert["event_type"] == "distraction"
            assert alert["distraction_type"] == "phone"
            assert "kss_now" in alert
            assert alert["kss_now"] is not None
        processor.close()


class TestFalsePositiveAndMissedAlertPrevention:
    """Validate specific physical test failure scenarios:
    1. Phone in view while looking straight ahead MUST NOT trigger alert.
    2. Looking at the phone MUST accumulate timer and trigger after threshold.
    3. Multimodal gaze + head pitch prevents false positives from head tilt alone.
    4. Recovery enables subsequent alerts for subsequent distraction episodes.
    """

    def setup_method(self):
        self.detector = PhoneDistractionDetector(
            min_duration_seconds=2.0,
            cooldown_seconds=5.0,
            pitch_threshold_deg=6.0,
            confidence_threshold=0.35,
        )

    def test_phone_visible_looking_straight_ahead_never_triggers(self):
        """Webcam Failure Case 1: Phone visible on dash/holder, driver looking straight at road.
        Head pitch is 0.0 or negative (-3.5 deg), iris vertical ratio ~0.50.
        Must NEVER trigger alert or increment distraction duration.
        """
        t0 = 1000.0
        for i in range(50):  # 5.0 seconds
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.89,
                phone_box=(200, 300, 350, 480),
                head_pitch_deg=-3.5,
                face_detected=True,
                gaze_vert_ratio=0.50,
                is_trip_active=True,
            )
            assert res["distraction_active"] is False
            assert res["distraction_confirmed"] is False
            assert res["triggered"] is False
            assert res["duration_seconds"] == 0.0
            assert res["phone_present"] is True
            assert res["looking_down"] is False

    def test_looking_at_phone_triggers_alert_after_configured_threshold(self):
        """Webcam Failure Case 2: Phone visible and driver tilts head down to look at phone.
        Head pitch is +14.0 deg (positive downward), gaze_vert_ratio is 0.65 (downward gaze).
        Distraction timer must increment and trigger alert at exactly 2.0s.
        """
        t0 = 1000.0
        triggered = False

        for i in range(25):  # 2.5 seconds
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(200, 300, 350, 480),
                head_pitch_deg=14.0,
                face_detected=True,
                gaze_vert_ratio=0.65,
                is_trip_active=True,
            )
            if i < 20:  # Before 2.0s
                assert res["distraction_confirmed"] is False
            else:  # At and after 2.0s
                assert res["distraction_confirmed"] is True
                assert res["distraction_active"] is True
                assert res["duration_seconds"] >= 2.0

            if res["triggered"]:
                triggered = True
                assert abs((t0 + i * 0.1) - (t0 + 2.0)) < 0.15

        assert triggered is True

    def test_iris_gaze_prevents_false_positive_when_head_tilted_slightly_down(self):
        """If driver tilts head slightly down (pitch=7.0 deg) but eyes remain up on road (gaze=0.46),
        multimodal check recognizes driver is attending to road, preventing false distraction.
        """
        t0 = 1000.0
        for i in range(30):
            res = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.80,
                phone_box=(200, 300, 350, 480),
                head_pitch_deg=7.5,
                face_detected=True,
                gaze_vert_ratio=0.46,  # Eyes directed straight/up toward road
                is_trip_active=True,
            )
            assert res["distraction_active"] is False
            assert res["distraction_confirmed"] is False
            assert res["triggered"] is False

    def test_recovery_enables_new_distraction_to_alert_subsequently(self):
        """Driver looks at phone (triggers alert 1), looks back at road (recovers),
        then looks back at phone (triggers alert 2).
        """
        t0 = 1000.0
        # Phase 1: Distraction episode 1 (2.3s)
        for i in range(24):
            res1 = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(200, 300, 350, 480),
                head_pitch_deg=15.0,
                face_detected=True,
                gaze_vert_ratio=0.65,
                is_trip_active=True,
            )
        assert res1["distraction_confirmed"] is True

        # Phase 2: Driver looks back at road for 1.5s
        for i in range(24, 39):
            res_rec = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(200, 300, 350, 480),
                head_pitch_deg=-2.0,
                face_detected=True,
                gaze_vert_ratio=0.50,
                is_trip_active=True,
            )
            assert res_rec["distraction_active"] is False
            assert res_rec["distraction_confirmed"] is False

        # Phase 3: Driver looks back down at phone for another 2.5s -> must trigger second alert
        second_triggered = False
        for i in range(39, 65):
            res2 = self.detector.update(
                now=t0 + i * 0.1,
                phone_detected=True,
                phone_confidence=0.85,
                phone_box=(200, 300, 350, 480),
                head_pitch_deg=16.0,
                face_detected=True,
                gaze_vert_ratio=0.66,
                is_trip_active=True,
            )
            if res2["triggered"]:
                second_triggered = True

        assert second_triggered is True
        assert res2["distraction_confirmed"] is True


class TestMultiClassObjectDetection:
    """Validate multi-object cabin detection and COCO class mapping."""

    def test_detect_objects_identifies_multiple_coco_classes(self):
        """Detect returns cell phones, bottles, cups, and laptops with correct labels."""
        mock_model = MagicMock()
        mock_boxes = torch.tensor([
            [10.0, 10.0, 80.0, 120.0],
            [100.0, 50.0, 160.0, 200.0],
            [200.0, 30.0, 270.0, 150.0],
        ], dtype=torch.float32)
        mock_scores = torch.tensor([0.88, 0.75, 0.82], dtype=torch.float32)
        mock_labels = torch.tensor([77, 44, 47], dtype=torch.int64)  # 77=phone, 44=bottle, 47=cup

        mock_model.return_value = [{
            "boxes": mock_boxes,
            "scores": mock_scores,
            "labels": mock_labels,
        }]

        detector = PhoneDetector(confidence_threshold=0.35, model=mock_model)
        frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        objects = detector.detect_objects(frame)

        assert len(objects) == 3
        class_names = [o["class_name"] for o in objects]
        assert "cell phone" in class_names
        assert "bottle" in class_names
        assert "cup" in class_names

    def test_detect_objects_target_classes_filter(self):
        """Target classes filter restricts output to requested IDs."""
        mock_model = MagicMock()
        mock_boxes = torch.tensor([
            [10.0, 10.0, 80.0, 120.0],
            [100.0, 50.0, 160.0, 200.0],
        ], dtype=torch.float32)
        mock_scores = torch.tensor([0.88, 0.75], dtype=torch.float32)
        mock_labels = torch.tensor([77, 44], dtype=torch.int64)  # phone and bottle

        mock_model.return_value = [{
            "boxes": mock_boxes,
            "scores": mock_scores,
            "labels": mock_labels,
        }]

        detector = PhoneDetector(confidence_threshold=0.35, model=mock_model)
        frame = np.full((480, 640, 3), 100, dtype=np.uint8)

        # Only request bottle (44)
        bottles = detector.detect_objects(frame, target_classes=[44])
        assert len(bottles) == 1
        assert bottles[0]["class_name"] == "bottle"

    def test_cabin_coco_classes_dictionary_defined(self):
        """Ensure CABIN_RELEVANT_COCO_CLASSES has appropriate mappings."""
        from app.distraction.config import CABIN_RELEVANT_COCO_CLASSES
        assert 77 in CABIN_RELEVANT_COCO_CLASSES
        assert CABIN_RELEVANT_COCO_CLASSES[77] == "cell phone"
        assert 44 in CABIN_RELEVANT_COCO_CLASSES
        assert CABIN_RELEVANT_COCO_CLASSES[44] == "bottle"
        assert 47 in CABIN_RELEVANT_COCO_CLASSES
        assert CABIN_RELEVANT_COCO_CLASSES[47] == "cup"



