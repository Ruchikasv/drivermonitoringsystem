"""
Tests for Monitoring Sessions, Incidents, Safety Ratings, and Evidence APIs.
"""

import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.database.connection import get_connection, init_db
from app.database.monitoring_repository import MonitoringRepository
from app.database.driver_repository import DriverRepository
from app.database.vehicle_repository import VehicleRepository


@pytest.fixture
def client():
    # Setup test DB in memory
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    # Seed test driver and vehicle
    import numpy as np
    dummy_emb = np.ones(512, dtype=np.float32).tobytes()
    d_repo = DriverRepository(conn)
    d_id = d_repo.add_driver(name="Test Driver", embedding=np.ones(512, dtype=np.float32))

    v_repo = VehicleRepository(conn)
    v_id = v_repo.add_vehicle(registration_number="KA-01-TEST", model="Test Truck", vehicle_type="Cargo")
    v_repo.assign_vehicle(driver_id=d_id, vehicle_id=v_id)

    # Override get_connection in app
    def _override_get_conn():
        return conn

    app.dependency_overrides[get_connection] = _override_get_conn

    # Also override repo dependencies if needed
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

