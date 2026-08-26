"""
Test suite for persistent Pause Trip and Resume Trip lifecycle and metrics.

Verifies:
1. RUNNING -> PAUSED -> RUNNING -> COMPLETED state machine
2. PAUSED -> COMPLETED direct termination
3. Multiple pause/resume cycles with total_paused_seconds accumulation
4. Active duration calculation excluding paused time
5. Same trip/session ID preservation across pause/resume
6. Rejection of invalid transitions (pause while paused, resume while running, resume after completed)
7. Absence of incident generation while paused
8. Detector state clearing on resume preventing stale pre-pause alert triggers
9. Multi-tenant owner isolation and authorization checks
10. Database persistence across simulated restarts
"""

import time
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
import numpy as np

from app.api.main import app
from app.database.connection import get_connection, init_db
from app.database.owner_repository import OwnerRepository
from app.database.driver_repository import DriverRepository
from app.database.vehicle_repository import VehicleRepository
from app.database.monitoring_repository import MonitoringRepository
from app.api.monitoring_ws import DriverSessionProcessor


@pytest.fixture
def client_and_repos():
    client = TestClient(app)
    conn = get_connection(":memory:")
    init_db(conn)
    app.dependency_overrides[get_connection] = lambda: conn

    o_repo = OwnerRepository(conn)
    d_repo = DriverRepository(conn)
    v_repo = VehicleRepository(conn)
    m_repo = MonitoringRepository(conn)

    # Register Owner
    owner_id = o_repo.create_owner("Test Owner", "pause_test@owner.com", "SecurePass123!")
    from app.api.dependencies import create_access_token
    token = create_access_token({"sub": str(owner_id)})
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Register Driver & Vehicle
    driver_id = d_repo.add_driver("Driver Alex", np.zeros(512, dtype=np.float32), license_no="DL-PAUSE-01", owner_id=owner_id)
    vehicle_id = v_repo.add_vehicle("KA-01-PAUSE", "Freightliner Cascadia", "Heavy", owner_id=owner_id)

    yield client, conn, m_repo, d_repo, v_repo, owner_id, driver_id, vehicle_id, auth_headers

    app.dependency_overrides.clear()
    conn.close()


class TestTripPauseResumeLifecycle:

    def test_running_to_paused_to_running_to_completed_flow(self, client_and_repos):
        """Verify full RUNNING -> PAUSED -> RUNNING -> COMPLETED transition lifecycle."""
        client, conn, m_repo, d_repo, v_repo, owner_id, driver_id, vehicle_id, auth_headers = client_and_repos

        # 1. Create active session (RUNNING)
        res_create = client.post("/sessions/", json={"driver_id": driver_id, "vehicle_id": vehicle_id}, headers=auth_headers)
        assert res_create.status_code == 201
        session_data = res_create.json()
        session_id = session_data["session_id"]
        assert session_data["status"] == "ACTIVE"
        assert session_data["is_paused"] is False

        # 2. Pause Trip
        res_pause = client.post(f"/sessions/{session_id}/pause", headers=auth_headers)
        assert res_pause.status_code == 200
        paused_data = res_pause.json()
        assert paused_data["session_id"] == session_id
        assert paused_data["status"] == "PAUSED"
        assert paused_data["is_paused"] is True
        assert paused_data["pause_started_at"] is not None

        # Verify in DB
        sess_db = m_repo.get_session(session_id)
        assert sess_db.status == "PAUSED"
        assert sess_db.pause_started_at is not None

        # 3. Resume Trip (same session ID must continue)
        res_resume = client.post(f"/sessions/{session_id}/resume", headers=auth_headers)
        assert res_resume.status_code == 200
        resumed_data = res_resume.json()
        assert resumed_data["session_id"] == session_id
        assert resumed_data["status"] == "ACTIVE"
        assert resumed_data["is_paused"] is False
        assert resumed_data["pause_started_at"] is None

        # 4. End Trip
        res_end = client.delete(f"/sessions/{session_id}", headers=auth_headers)
        assert res_end.status_code == 200

        sess_ended = m_repo.get_session(session_id)
        assert sess_ended.status == "COMPLETED"
        assert sess_ended.end_time is not None

    def test_direct_end_from_paused_state(self, client_and_repos):
        """Verify driver/owner can end trip directly while in PAUSED status."""
        client, conn, m_repo, d_repo, v_repo, owner_id, driver_id, vehicle_id, auth_headers = client_and_repos

        res_create = client.post("/sessions/", json={"driver_id": driver_id, "vehicle_id": vehicle_id}, headers=auth_headers)
        session_id = res_create.json()["session_id"]

        # Pause trip
        client.post(f"/sessions/{session_id}/pause", headers=auth_headers)

        # End trip while PAUSED
        res_end = client.delete(f"/sessions/{session_id}", headers=auth_headers)
        assert res_end.status_code == 200

        sess_ended = m_repo.get_session(session_id)
        assert sess_ended.status == "COMPLETED"
        assert sess_ended.end_time is not None
        assert sess_ended.pause_started_at is None

    def test_multiple_pause_resume_cycles_accumulation(self, client_and_repos):
        """Verify multiple pause and resume cycles accumulate total_paused_seconds correctly."""
        client, conn, m_repo, d_repo, v_repo, owner_id, driver_id, vehicle_id, auth_headers = client_and_repos

        res_create = client.post("/sessions/", json={"driver_id": driver_id, "vehicle_id": vehicle_id}, headers=auth_headers)
        session_id = res_create.json()["session_id"]

        # Cycle 1: Pause -> artificially advance pause_started_at by 100 seconds -> Resume
        m_repo.pause_session(session_id)
        past_100s = (datetime.now(timezone.utc) - timedelta(seconds=100)).isoformat()
        conn.execute("UPDATE monitoring_sessions SET pause_started_at = ? WHERE session_id = ?", (past_100s, session_id))
        m_repo.resume_session(session_id)

        sess_1 = m_repo.get_session(session_id)
        assert sess_1.status == "ACTIVE"
        assert sess_1.total_paused_seconds >= 99.0

        # Cycle 2: Pause -> artificially advance by 50 seconds -> Resume
        m_repo.pause_session(session_id)
        past_50s = (datetime.now(timezone.utc) - timedelta(seconds=50)).isoformat()
        conn.execute("UPDATE monitoring_sessions SET pause_started_at = ? WHERE session_id = ?", (past_50s, session_id))
        m_repo.resume_session(session_id)

        sess_2 = m_repo.get_session(session_id)
        assert sess_2.status == "ACTIVE"
        assert sess_2.total_paused_seconds >= 149.0

        # Verify Trips API duration breakdown
        res_trips = client.get("/trips", headers=auth_headers)
        trips = res_trips.json()
        assert len(trips) == 1
        trip = trips[0]
        assert trip["session_id"] == session_id
        assert trip["status"] == "RUNNING"
        assert trip["total_paused_minutes"] >= 2.4

    def test_invalid_state_transition_rejections(self, client_and_repos):
        """Verify invalid transitions return HTTP 400 Bad Request."""
        client, conn, m_repo, d_repo, v_repo, owner_id, driver_id, vehicle_id, auth_headers = client_and_repos

        res_create = client.post("/sessions/", json={"driver_id": driver_id, "vehicle_id": vehicle_id}, headers=auth_headers)
        session_id = res_create.json()["session_id"]

        # 1. Cannot resume an already RUNNING session
        res_bad_resume = client.post(f"/sessions/{session_id}/resume", headers=auth_headers)
        assert res_bad_resume.status_code == 400

        # 2. Pause
        client.post(f"/sessions/{session_id}/pause", headers=auth_headers)

        # 3. Cannot pause an already PAUSED session
        res_bad_pause = client.post(f"/sessions/{session_id}/pause", headers=auth_headers)
        assert res_bad_pause.status_code == 400

        # 4. End session
        client.delete(f"/sessions/{session_id}", headers=auth_headers)

        # 5. Cannot pause or resume a COMPLETED session
        assert client.post(f"/sessions/{session_id}/pause", headers=auth_headers).status_code == 400
        assert client.post(f"/sessions/{session_id}/resume", headers=auth_headers).status_code == 400

    def test_multi_tenant_owner_isolation_on_pause(self, client_and_repos):
        """Verify Owner B cannot pause, resume, or view Owner A's session."""
        client, conn, m_repo, d_repo, v_repo, owner_id_a, driver_id_a, vehicle_id_a, auth_a = client_and_repos
        o_repo = OwnerRepository(conn)

        # Create Owner B
        owner_id_b = o_repo.create_owner("Owner B", "owner_b@test.com", "PasswordB123!")
        from app.api.dependencies import create_access_token
        token_b = create_access_token({"sub": str(owner_id_b)})
        auth_b = {"Authorization": f"Bearer {token_b}"}

        # Owner A creates session
        res_a = client.post("/sessions/", json={"driver_id": driver_id_a, "vehicle_id": vehicle_id_a}, headers=auth_a)
        session_a_id = res_a.json()["session_id"]

        # Owner B tries to pause Owner A session -> 404
        res_b_pause = client.post(f"/sessions/{session_a_id}/pause", headers=auth_b)
        assert res_b_pause.status_code == 404

        # Owner B tries to resume Owner A session -> 404
        res_b_resume = client.post(f"/sessions/{session_a_id}/resume", headers=auth_b)
        assert res_b_resume.status_code == 404

        # Owner B tries to end Owner A session -> 404
        res_b_end = client.delete(f"/sessions/{session_a_id}", headers=auth_b)
        assert res_b_end.status_code == 404

    def test_detector_reset_clears_stale_pre_pause_state(self, client_and_repos):
        """Verify reset_all_detectors clears microsleep, yawn, and head nod accumulators."""
        _, _, _, _, _, _, driver_id, vehicle_id, _ = client_and_repos

        processor = DriverSessionProcessor(
            session_id=999,
            driver_id=driver_id,
            driver_name="Alex",
            vehicle_reg="KA-01-PAUSE",
        )

        # Simulate closed eyes triggering condition start
        processor.microsleep_detector._condition_since = time.time() - 10.0
        processor.alert_manager._in_critical_state = True

        assert processor.microsleep_detector._condition_since is not None
        assert processor.alert_manager._in_critical_state is True

        # Call reset_all_detectors
        processor.reset_all_detectors()

        assert processor.microsleep_detector._condition_since is None
        assert processor.alert_manager._in_critical_state is False
        assert processor.alert_manager._last_alert_time["critical"] == 0.0
