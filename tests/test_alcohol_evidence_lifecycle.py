"""
Unit and integration tests for alcohol-lockout evidence capture, storage,
API delivery, multi-tenant security, and deletion lifecycle.
"""

import os
import sqlite3
from pathlib import Path
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.owner_repository import OwnerRepository
from app.database.vehicle_repository import VehicleRepository
from app.drowsiness.evidence import generate_alcohol_lockout_evidence
from app.hardware.alcohol_sensor import MQ3SerialReader
from app.api.dependencies import create_access_token


@pytest.fixture
def test_db():
    """Set up an in-memory SQLite database."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    # Add owner
    o_repo = OwnerRepository(conn)
    owner_id = o_repo.create_owner(name="Test Owner", email="owner@test.com", plain_password="Password123!")
    test_owner = o_repo.get_owner_by_id(owner_id)

    # Add driver
    dummy_emb = np.ones(512, dtype=np.float32)
    d_repo = DriverRepository(conn)
    driver_id = d_repo.add_driver(name="John Driver", embedding=dummy_emb, owner_id=owner_id)

    # Add vehicle
    v_repo = VehicleRepository(conn)
    vehicle_id = v_repo.add_vehicle(registration_number="KA-01-AB-1234", model="Test Truck", vehicle_type="Cargo", owner_id=owner_id)
    v_repo.assign_vehicle(driver_id=driver_id, vehicle_id=vehicle_id, owner_id=owner_id)

    # Add session
    cur = conn.execute(
        "INSERT INTO monitoring_sessions (driver_id, owner_id, vehicle_id, start_time, status) VALUES (?, ?, ?, '2026-10-22T00:00:00', 'ACTIVE')",
        (driver_id, owner_id, vehicle_id),
    )
    session_id = cur.lastrowid
    conn.commit()

    yield {
        "conn": conn,
        "owner_id": owner_id,
        "driver_id": driver_id,
        "vehicle_id": vehicle_id,
        "session_id": session_id,
        "test_owner": test_owner,
    }
    conn.close()


def test_generate_alcohol_lockout_evidence_with_frame(tmp_path):
    """Test generating alcohol evidence with a camera frame produces both raw and warning files."""
    dummy_frame = np.full((480, 640, 3), 120, dtype=np.uint8)
    cv2.circle(dummy_frame, (320, 240), 50, (255, 0, 0), -1)

    warn_rel, raw_rel = generate_alcohol_lockout_evidence(
        frame_bgr=dummy_frame,
        driver_name="Test Driver",
        driver_id=1,
        vehicle_registration="KA-01-TEST",
        session_id=10,
        analog_value=350,
        threshold_value=200,
    )

    assert warn_rel is not None
    assert raw_rel is not None
    assert "_alcohol_warning.jpg" in warn_rel
    assert "_alcohol_raw.jpg" in raw_rel

    warn_full = settings.PROJECT_ROOT / warn_rel
    raw_full = settings.PROJECT_ROOT / raw_rel

    assert warn_full.exists()
    assert raw_full.exists()
    assert warn_full.stat().st_size > 0
    assert raw_full.stat().st_size > 0

    # Clean up created files
    warn_full.unlink(missing_ok=True)
    raw_full.unlink(missing_ok=True)


def test_generate_alcohol_lockout_evidence_without_frame():
    """Test generating alcohol evidence without a camera frame creates warning composite with notice."""
    warn_rel, raw_rel = generate_alcohol_lockout_evidence(
        frame_bgr=None,
        driver_name="Test Driver",
        driver_id=1,
        vehicle_registration="KA-01-TEST",
        session_id=10,
        analog_value=350,
        threshold_value=200,
    )

    assert warn_rel is not None
    assert raw_rel is None
    assert "_alcohol_warning.jpg" in warn_rel

    warn_full = settings.PROJECT_ROOT / warn_rel
    assert warn_full.exists()

    # Clean up
    warn_full.unlink(missing_ok=True)


def test_incident_api_dual_evidence_delivery_and_deletion(test_db):
    """Integration test verifying API delivery of raw and warning screenshots, token auth, and deletion."""
    conn = test_db["conn"]
    owner_id = test_db["owner_id"]
    driver_id = test_db["driver_id"]
    vehicle_id = test_db["vehicle_id"]
    session_id = test_db["session_id"]
    o_repo = OwnerRepository(conn)

    # Generate dummy frame and evidence
    dummy_frame = np.full((480, 640, 3), 150, dtype=np.uint8)
    warn_rel, raw_rel = generate_alcohol_lockout_evidence(
        frame_bgr=dummy_frame,
        driver_name="John Driver",
        driver_id=driver_id,
        vehicle_registration="KA-01-AB-1234",
        session_id=session_id,
        analog_value=320,
        threshold_value=200,
    )

    # Insert incident
    cur = conn.execute(
        """
        INSERT INTO monitoring_incidents
          (session_id, driver_id, vehicle_id, owner_id, timestamp, event_type, alert_level,
           kss_score, evidence_path, distraction_type)
        VALUES (?, ?, ?, ?, '2026-10-22T01:00:00', 'alcohol_detected', 3, 9.0, ?, 'MQ-3 Analog: 320 (Threshold: 200)')
        """,
        (session_id, driver_id, vehicle_id, owner_id, warn_rel),
    )
    conn.commit()
    inc_id = cur.lastrowid

    # Override get_connection in FastAPI app
    app.dependency_overrides[get_connection] = lambda: conn
    from app.api.incidents import _get_repos
    def _override_repos():
        yield conn, MonitoringRepository(conn), DriverRepository(conn)
    app.dependency_overrides[_get_repos] = _override_repos
    token = create_access_token(data={"sub": str(owner_id)})
    headers = {"Authorization": f"Bearer {token}"}

    client = TestClient(app)

    try:
        # 1. Fetch incident details
        res = client.get(f"/incidents/{inc_id}", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["has_evidence"] is True
        assert data["has_raw_evidence"] is True
        assert data["has_warning_evidence"] is True
        assert data["evidence_status"] == "AVAILABLE"
        assert data["raw_evidence_path"] == raw_rel
        assert data["warning_evidence_path"] == warn_rel

        # 2. Fetch warning screenshot via GET /incidents/{id}/evidence?type=warning
        w_res = client.get(f"/incidents/{inc_id}/evidence?type=warning", headers=headers)
        assert w_res.status_code == 200
        assert w_res.headers["content-type"] == "image/jpeg"
        assert len(w_res.content) > 0

        # 3. Fetch raw camera screenshot via GET /incidents/{id}/evidence?type=raw
        r_res = client.get(f"/incidents/{inc_id}/evidence?type=raw", headers=headers)
        assert r_res.status_code == 200
        assert r_res.headers["content-type"] == "image/jpeg"
        assert len(r_res.content) > 0

        # 4. Fetch via query token (for direct <img> tags)
        q_res = client.get(f"/incidents/{inc_id}/evidence?type=raw&token={token}")
        assert q_res.status_code == 200
        assert q_res.headers["content-type"] == "image/jpeg"

        # 5. Multi-tenant isolation test: another genuine fleet owner cannot view this evidence
        other_owner_id = o_repo.create_owner(name="Other Owner", email="other@test.com", plain_password="Password123!")
        other_token = create_access_token(data={"sub": str(other_owner_id)})
        iso_res = client.get(f"/incidents/{inc_id}/evidence", headers={"Authorization": f"Bearer {other_token}"})
        assert iso_res.status_code == 404

        # 6. Delete evidence
        del_res = client.delete(f"/incidents/{inc_id}/evidence", headers=headers)
        assert del_res.status_code == 200

        # Verify physical files are both deleted from disk
        warn_full = settings.PROJECT_ROOT / warn_rel
        raw_full = settings.PROJECT_ROOT / raw_rel
        assert not warn_full.exists()
        assert not raw_full.exists()

        # Verify incident now reflects NOT_CAPTURED / evidence_path=None
        after_res = client.get(f"/incidents/{inc_id}", headers=headers)
        assert after_res.status_code == 200
        after_data = after_res.json()
        assert after_data["has_evidence"] is False
        assert after_data["evidence_status"] == "NOT_CAPTURED"

    finally:
        app.dependency_overrides.clear()
        (settings.PROJECT_ROOT / warn_rel).unlink(missing_ok=True)
        (settings.PROJECT_ROOT / raw_rel).unlink(missing_ok=True)


def test_missing_evidence_file_reports_removed_status(test_db):
    """When evidence_path exists in DB but file was removed from disk, status is REMOVED."""
    conn = test_db["conn"]
    owner_id = test_db["owner_id"]
    driver_id = test_db["driver_id"]
    session_id = test_db["session_id"]

    non_existent_rel = "data/evidence/ghost_evidence_d1_s1.jpg"
    cur = conn.execute(
        """
        INSERT INTO monitoring_incidents
          (session_id, driver_id, owner_id, timestamp, event_type, alert_level,
           evidence_path, distraction_type)
        VALUES (?, ?, ?, '2026-10-22T01:00:00', 'critical', 3, ?, 'Ghost')
        """,
        (session_id, driver_id, owner_id, non_existent_rel),
    )
    conn.commit()
    inc_id = cur.lastrowid

    app.dependency_overrides[get_connection] = lambda: conn
    from app.api.incidents import _get_repos
    def _override_repos():
        yield conn, MonitoringRepository(conn), DriverRepository(conn)
    app.dependency_overrides[_get_repos] = _override_repos
    token = create_access_token(data={"sub": str(owner_id)})
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)

    try:
        res = client.get(f"/incidents/{inc_id}", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["has_evidence"] is False
        assert data["evidence_status"] == "REMOVED"
    finally:
        app.dependency_overrides.clear()
