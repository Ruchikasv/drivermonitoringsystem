"""
Tests for Monitoring Sessions, Incidents, Safety Ratings, and Evidence APIs.
"""

import base64
import os
import sqlite3
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_owner
from app.api.main import app
from app.config import settings
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.owner_repository import OwnerRecord, OwnerRepository
from app.database.vehicle_repository import VehicleRepository


@pytest.fixture
def client():
    # Setup test DB in memory
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    # Create test owner
    o_repo = OwnerRepository(conn)
    owner_id = o_repo.create_owner(name="Test Owner", email="owner@test.com", plain_password="Password123!")
    test_owner = o_repo.get_owner_by_id(owner_id)

    # Seed test driver and vehicle
    dummy_emb = np.ones(512, dtype=np.float32)
    d_repo = DriverRepository(conn)
    d_id = d_repo.add_driver(name="Test Driver", embedding=dummy_emb, owner_id=owner_id)

    v_repo = VehicleRepository(conn)
    v_id = v_repo.add_vehicle(registration_number="KA-01-TEST", model="Test Truck", vehicle_type="Cargo", owner_id=owner_id)
    v_repo.assign_vehicle(driver_id=d_id, vehicle_id=v_id, owner_id=owner_id)

    # Override dependencies
    app.dependency_overrides[get_connection] = lambda: conn
    app.dependency_overrides[get_current_owner] = lambda: test_owner

    from app.api.monitoring import _get_repo as _get_m_repo
    from app.api.incidents import _get_repo as _get_i_repo

    def _override_m_repo():
        yield MonitoringRepository(conn)

    app.dependency_overrides[_get_m_repo] = _override_m_repo
    app.dependency_overrides[_get_i_repo] = _override_m_repo

    test_client = TestClient(app)
    yield test_client, conn

    app.dependency_overrides.clear()
    conn.close()



def test_session_lifecycle(client):
    test_client, conn = client
    # 1. Create session
    res = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1})
    assert res.status_code == 201
    data = res.json()
    assert data["session_id"] is not None
    assert data["driver_id"] == 1
    assert data["status"] == "ACTIVE"
    session_id = data["session_id"]

    # 2. Get active sessions
    res = test_client.get("/sessions/active")
    assert res.status_code == 200
    active = res.json()
    assert any(s["session_id"] == session_id for s in active)

    # 3. Get single session
    res = test_client.get(f"/sessions/{session_id}")
    assert res.status_code == 200
    assert res.json()["status"] == "ACTIVE"

    # 4. End session
    res = test_client.delete(f"/sessions/{session_id}")
    assert res.status_code == 200
    assert "completed" in res.json()["message"]

    # 5. Verify no longer in active
    res = test_client.get("/sessions/active")
    active = res.json()
    assert not any(s["session_id"] == session_id for s in active)


def test_incident_and_safety_rating_flow(client):
    test_client, conn = client
    # Create session
    s_res = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1}).json()
    session_id = s_res["session_id"]

    # Log incident via DB directly using the test connection
    repo = MonitoringRepository(conn)
    inc_id = repo.create_incident(
        session_id=session_id,
        driver_id=1,
        vehicle_id=1,
        event_type="critical",
        alert_level=3,
        kss_score=8.5,
        ear=0.08,
        mar=0.30,
        perclos=0.45,
        head_pitch_deg=-18.5,
        evidence_path=None,
    )


    # 1. List incidents
    res = test_client.get("/incidents/")
    assert res.status_code == 200
    incidents = res.json()
    assert len(incidents) >= 1
    assert incidents[0]["incident_id"] == inc_id
    assert incidents[0]["event_type"] == "critical"

    # 2. Driver-specific incidents
    res = test_client.get("/incidents/driver/1")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 3. End session and check recalculated safety rating
    test_client.delete(f"/sessions/{session_id}")
    rating_res = test_client.get("/incidents/driver/1/rating")
    assert rating_res.status_code == 200
    r_data = rating_res.json()
    assert r_data["total_sessions"] == 1
    assert r_data["total_incidents"] == 1
    assert r_data["critical_incidents"] == 1
    # 100 - (1 critical * 8) = 92.0
    assert r_data["safety_score"] == 92.0


def test_driver_status_reflects_session_state(client):
    test_client, conn = client
    
    # 1. Driver starts with OFF_DUTY
    d_res = test_client.get("/drivers/1")
    assert d_res.status_code == 200
    assert d_res.json()["status"] == "OFF_DUTY"

    # 2. Driver starts a session -> ON_ROUTE
    s_res = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1}).json()
    session_id = s_res["session_id"]
    d_res = test_client.get("/drivers/1")
    assert d_res.status_code == 200
    assert d_res.json()["status"] == "ON_ROUTE"

    # 3. Driver ends session -> OFF_DUTY
    test_client.delete(f"/sessions/{session_id}")
    d_res = test_client.get("/drivers/1")
    assert d_res.status_code == 200
    assert d_res.json()["status"] == "OFF_DUTY"
    assert d_res.json()["total_trips"] == 1


def test_trips_api(client):
    test_client, conn = client
    
    # Create and complete a session
    s_res = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1}).json()
    session_id = s_res["session_id"]
    test_client.delete(f"/sessions/{session_id}")

    # Query /trips
    res = test_client.get("/trips")
    assert res.status_code == 200
    trips = res.json()
    assert len(trips) >= 1
    trip = trips[0]
    assert trip["driver_id"] == 1
    assert trip["driver_name"] == "Test Driver"
    assert trip["status"] == "COMPLETED"
    assert trip["vehicle_plate"] == "KA-01-TEST"


def test_alerts_api(client):
    test_client, conn = client
    
    # Create session & log incident
    s_res = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1}).json()
    session_id = s_res["session_id"]
    repo = MonitoringRepository(conn)
    repo.create_incident(
        session_id=session_id,
        driver_id=1,
        vehicle_id=1,
        event_type="warning",
        alert_level=2,
        kss_score=6.5,
        ear=0.18,
        mar=0.60,
    )

    # Query /alerts
    res = test_client.get("/alerts")
    assert res.status_code == 200
    alerts = res.json()
    assert len(alerts) >= 1
    assert alerts[0]["level"] == 2
    assert alerts[0]["event_type"] == "Warning"
    assert alerts[0]["driver_name"] == "Test Driver"


def test_analytics_api(client):
    test_client, conn = client

    # Query metrics
    res = test_client.get("/analytics/metrics")
    assert res.status_code == 200
    metrics = res.json()
    assert "total_drivers" in metrics
    assert "active_trips" in metrics
    assert "average_safety_score" in metrics

    # Query alerts by driver
    res = test_client.get("/analytics/alerts-by-driver")
    assert res.status_code == 200
    by_driver = res.json()
    assert len(by_driver) >= 1
    assert by_driver[0]["name"] == "Test Driver"

    # Query score distribution
    res = test_client.get("/analytics/score-distribution")
    assert res.status_code == 200
    dist = res.json()
    assert len(dist) == 4

    # Query drowsiness trend
    res = test_client.get("/analytics/drowsiness-trend")
    assert res.status_code == 200
    trend = res.json()
    assert len(trend) == 7


def test_prevent_duplicate_active_sessions_for_same_driver(client):
    test_client, conn = client
    repo = MonitoringRepository(conn)

    # 1. Start Trip 1 for Driver 1
    res1 = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1})
    assert res1.status_code == 201
    s1_id = res1.json()["session_id"]
    assert res1.json()["status"] == "ACTIVE"

    # 2. Start Trip 2 for Driver 1 without ending Trip 1
    res2 = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1})
    assert res2.status_code == 201
    s2_id = res2.json()["session_id"]
    assert res2.json()["status"] == "ACTIVE"
    assert s2_id != s1_id

    # 3. Verify Trip 1 was automatically closed as INTERRUPTED with an end_time
    s1 = repo.get_session(s1_id)
    assert s1.status == "INTERRUPTED"
    assert s1.end_time is not None

    # 4. Verify only Trip 2 is returned by GET /sessions/active
    active_res = test_client.get("/sessions/active")
    assert active_res.status_code == 200
    active_sessions = active_res.json()
    driver1_active = [s for s in active_sessions if s["driver_id"] == 1]
    assert len(driver1_active) == 1
    assert driver1_active[0]["session_id"] == s2_id

    # 5. Verify database-level unique constraint prevents manual duplicate active inserts
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO monitoring_sessions (driver_id, vehicle_id, start_time, status) VALUES (1, 1, '2026-08-25T00:00:00', 'ACTIVE')"
        )


def test_driver_becomes_off_duty_after_end_trip(client):
    test_client, conn = client

    # Start session
    s_res = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1}).json()
    session_id = s_res["session_id"]

    # Verify driver is ON_ROUTE
    d_res = test_client.get("/drivers/1").json()
    assert d_res["status"] == "ON_ROUTE"

    # End session (END TRIP)
    del_res = test_client.delete(f"/sessions/{session_id}")
    assert del_res.status_code == 200

    # Verify driver is immediately OFF_DUTY
    d_res = test_client.get("/drivers/1").json()
    assert d_res["status"] == "OFF_DUTY"

    # Verify session is not in active sessions
    active_res = test_client.get("/sessions/active").json()
    assert not any(s["session_id"] == session_id for s in active_res)


def test_websocket_interruption_marks_session_interrupted(client):
    test_client, conn = client
    repo = MonitoringRepository(conn)

    # Start session
    s_res = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1}).json()
    session_id = s_res["session_id"]

    # Simulate WebSocket disconnection cleanup
    repo.interrupt_session(session_id)
    repo.recalculate_safety_rating(1)

    # Verify session status in DB
    session = repo.get_session(session_id)
    assert session.status == "INTERRUPTED"
    assert session.end_time is not None

    # Verify driver status is OFF_DUTY
    d_res = test_client.get("/drivers/1").json()
    assert d_res["status"] == "OFF_DUTY"

    # Verify active sessions excludes it
    active_res = test_client.get("/sessions/active").json()
    assert not any(s["session_id"] == session_id for s in active_res)


def test_get_active_sessions_excludes_completed_and_interrupted(client):
    test_client, conn = client
    repo = MonitoringRepository(conn)

    # Seed an extra driver for multi-driver testing
    d_repo = DriverRepository(conn)
    d2_id = d_repo.add_driver(name="Second Driver", embedding=np.ones(512, dtype=np.float32))

    # Session 1 for Driver 1: Completed
    s1_id = repo.create_session(1, 1)
    repo.end_session(s1_id, status="COMPLETED")

    # Session 2 for Driver 1: Interrupted
    s2_id = repo.create_session(1, 1)
    repo.end_session(s2_id, status="INTERRUPTED")

    # Session 3 for Driver 2: Active
    s3_id = repo.create_session(d2_id, 1)

    active_res = test_client.get("/sessions/active").json()
    active_ids = [s["session_id"] for s in active_res]
    assert s1_id not in active_ids
    assert s2_id not in active_ids
    assert s3_id in active_ids
    assert len(active_ids) == 1


def test_websocket_monitoring_processes_browser_frames(client):
    test_client, conn = client

    # 1. Start a session
    s_res = test_client.post("/sessions/", json={"driver_id": 1, "vehicle_id": 1}).json()
    session_id = s_res["session_id"]
    token = s_res.get("session_token")
    token_query = f"?token={token}" if token else ""

    # 2. Connect via TestClient WebSocket
    with test_client.websocket_connect(f"/ws/monitor/{session_id}{token_query}") as ws:
        # Send a synthetic frame
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        _, buffer = cv2.imencode(".jpg", img)
        frame_b64 = base64.b64encode(buffer).decode("utf-8")

        ws.send_json({"frame": frame_b64})

        res_data = ws.receive_json()
        assert res_data["session_id"] == session_id
        assert res_data["driver_id"] == 1
        assert "metrics" in res_data
        assert "fusion" in res_data


def test_delete_incident_evidence(client, tmp_path):
    test_client, conn = client
    repo = MonitoringRepository(conn)

    # 1. Create a dummy evidence file in app/evidence
    evidence_dir = os.path.join(str(settings.PROJECT_ROOT), "app", "evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    evidence_file = os.path.join(evidence_dir, "test_evidence_dummy.jpg")
    with open(evidence_file, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb")

    rel_path = os.path.relpath(evidence_file, str(settings.PROJECT_ROOT))

    # 2. Create an incident with evidence_path
    session_id = repo.create_session(1, 1)
    inc_id = repo.create_incident(
        session_id=session_id,
        driver_id=1,
        vehicle_id=1,
        event_type="critical",
        alert_level=3,
        kss_score=8.5,
        ear=0.15,
        mar=0.30,
        evidence_path=rel_path,
    )

    assert os.path.exists(evidence_file)

    # 3. Call DELETE /incidents/{incident_id}/evidence
    del_res = test_client.delete(f"/incidents/{inc_id}/evidence")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # 4. Verify physical file is deleted and DB evidence_path is NULL
    assert not os.path.exists(evidence_file)
    inc = repo.get_incident(inc_id)
    assert inc is not None
    assert inc.evidence_path is None


def test_fire_driver_cascading_deletion(client):
    test_client, conn = client
    d_repo = DriverRepository(conn)
    v_repo = VehicleRepository(conn)
    m_repo = MonitoringRepository(conn)

    # 1. Register a driver
    driver_id = d_repo.add_driver(name="Driver To Fire", embedding=np.zeros(512, dtype=np.float32), owner_id=1)

    # 2. Assign a vehicle
    v_id = v_repo.add_vehicle(registration_number="KA-04-FIRE-01", vehicle_type="Truck", model="Fleet Truck Alpha", owner_id=1)
    v_repo.assign_vehicle(driver_id, v_id, owner_id=1)
    assert v_repo.get_current_assignment(driver_id) is not None

    # 3. Create session, incident, evidence file, and safety rating
    s_id = m_repo.create_session(driver_id, v_id)
    evidence_dir = os.path.join(str(settings.PROJECT_ROOT), "app", "evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    evidence_file = os.path.join(evidence_dir, f"evidence_driver_{driver_id}.jpg")
    with open(evidence_file, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb")
    rel_path = os.path.relpath(evidence_file, str(settings.PROJECT_ROOT))

    inc_id = m_repo.create_incident(
        session_id=s_id,
        driver_id=driver_id,
        vehicle_id=v_id,
        event_type="critical",
        alert_level=3,
        evidence_path=rel_path,
    )
    m_repo.recalculate_safety_rating(driver_id)

    # 4. Fire driver via DELETE /drivers/{driver_id}
    del_res = test_client.delete(f"/drivers/{driver_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # 5. Verify Driver is deactivated from active fleet
    assert d_repo.get_driver_by_id(driver_id) is None

    # 6. Verify Vehicle is NOT deleted, but is unassigned (available in fleet)
    veh = v_repo.get_vehicle_by_id(v_id)
    assert veh is not None
    assert v_repo.get_current_assignment(driver_id) is None

    # 7. Verify biometrics are wiped and active session was closed
    raw_row = conn.execute("SELECT face_embedding, is_active, deleted_at FROM drivers WHERE driver_id = ?", (driver_id,)).fetchone()
    assert raw_row["face_embedding"] is None
    assert raw_row["is_active"] == 0
    assert raw_row["deleted_at"] is not None

    sess = m_repo.get_session(s_id)
    assert sess.status == "INTERRUPTED"

    # 8. Verify GET /drivers does not contain the deleted driver
    drivers_list = test_client.get("/drivers").json()
    assert not any(d["driver_id"] == driver_id for d in drivers_list)


def test_driver_session_processor_process_frame_with_config():
    """Verify DriverSessionProcessor runs process_frame without NameError on config."""
    from app.api.monitoring_ws import DriverSessionProcessor
    processor = DriverSessionProcessor(
        session_id=999,
        driver_id=1,
        driver_name="Test Driver",
        vehicle_reg="KA-01-MJ-8821",
    )

    # Frame with no face (blank image)
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    annotated, metrics, alert = processor.process_frame(dummy_frame)

    assert annotated.shape == (480, 640, 3)
    assert metrics["face_detected"] is False
    assert metrics["fusion"]["kss_now"] == 1.0

    # Clean up
    processor.close()




