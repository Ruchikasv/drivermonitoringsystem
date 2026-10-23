import sqlite3
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api.main import app
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.database.vehicle_repository import VehicleRepository
from app.database.owner_repository import OwnerRepository
from app.database.monitoring_repository import MonitoringRepository
from app.face_recognition.detector import DetectedFace

@pytest.fixture
def test_setup():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    from app.api.dependencies import get_current_owner, get_optional_owner
    from app.api.auth import _get_db
    from app.api.monitoring import _get_repo

    o_repo = OwnerRepository(conn)
    owner_id = o_repo.create_owner("Test Owner", "owner@regression.com", "Password123!")
    test_owner = o_repo.get_owner_by_id(owner_id)

    d_repo = DriverRepository(conn)
    base_emb = np.zeros(512, dtype=np.float32)
    base_emb[0] = 1.0
    driver_id = d_repo.add_driver(name="Test Driver", embedding=base_emb, license_no="DL-REG-8821", owner_id=owner_id)

    v_repo = VehicleRepository(conn)
    vehicle_id = v_repo.add_vehicle(registration_number="KA-01-MJ-8821", model="Tata Prima", vehicle_type="Truck", owner_id=owner_id)
    v_repo.assign_vehicle(driver_id=driver_id, vehicle_id=vehicle_id, owner_id=owner_id)

    m_repo = MonitoringRepository(conn)

    app.dependency_overrides[get_connection] = lambda: conn
    app.dependency_overrides[_get_db] = lambda: conn
    app.dependency_overrides[_get_repo] = lambda: m_repo
    app.dependency_overrides[get_current_owner] = lambda: test_owner
    app.dependency_overrides[get_optional_owner] = lambda: test_owner

    client = TestClient(app)
    yield client, conn, driver_id, vehicle_id, base_emb

    app.dependency_overrides.clear()
    conn.close()

def test_cors_headers_localhost_and_127(test_setup):
    """Confirm CORS headers allow both localhost:5173 and 127.0.0.1:5173."""
    client, _, _, _, _ = test_setup
    for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
        response = client.options(
            "/sessions/active",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,Content-Type"
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin
        assert response.headers.get("access-control-allow-credentials") == "true"

def test_driver_monitoring_start_and_grace_period(test_setup):
    """
    Test the driver monitoring start flow:
    1. Authenticate driver -> session_id returned
    2. Validate session via GET /sessions/{session_id}
    3. Connect WebSocket -> verify active connection
    4. Disconnect -> verify session is NOT immediately killed due to grace period
    5. Reconnect -> succeeds cleanly
    """
    client, conn, driver_id, vehicle_id, base_emb = test_setup

    detected = DetectedFace(
        bbox=np.array([50, 50, 150, 150]),
        score=0.98,
        embedding=base_emb
    )

    with patch("app.api.auth._decode_frame", return_value=np.zeros((100, 100, 3), dtype=np.uint8)), \
         patch("app.api.auth._get_detector") as mock_get_detector:
        mock_d = MagicMock()
        mock_d.detect_single_face.return_value = detected
        mock_get_detector.return_value = mock_d

        auth_res = client.post("/auth/authenticate", json={"frame_b64": "data:image/jpeg;base64,fake"})
        assert auth_res.status_code == 200
        auth_data = auth_res.json()
        assert auth_data.get("driver_id") == driver_id
        session_id = auth_data.get("session_id")
        session_token = auth_data.get("session_token")
        assert session_id is not None
        assert session_token is not None

    # Step 2: Validate session via GET /sessions/{session_id}
    sess_res = client.get(
        f"/sessions/{session_id}",
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert sess_res.status_code == 200
    sess_data = sess_res.json()
    assert sess_data["session_id"] == session_id
    assert sess_data["status"] == "ACTIVE"
    assert sess_data["is_locked"] is False

    # Step 3: Connect WebSocket
    with client.websocket_connect(f"/ws/monitor/{session_id}?token={session_token}") as ws:
        pass

    # Step 4: Verify session remains ACTIVE after disconnect due to grace period
    sess_after = client.get(
        f"/sessions/{session_id}",
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert sess_after.status_code == 200
    assert sess_after.json()["status"] == "ACTIVE"

    # Step 5: Reconnecting succeeds
    with client.websocket_connect(f"/ws/monitor/{session_id}?token={session_token}") as ws2:
        pass

def test_alcohol_lockout_returns_http_423(test_setup):
    """
    Test that when alcohol sensor detects lockout, session creation / resume returns HTTP 423
    with a clear explanation so frontend does not show a cryptic Network Error.
    """
    client, conn, driver_id, vehicle_id, _ = test_setup

    with patch("app.hardware.alcohol_sensor.mq3_serial_reader.is_locked", return_value=True):
        res = client.post("/sessions", json={
            "driver_id": driver_id,
            "vehicle_id": vehicle_id
        })
        assert res.status_code == 423
        assert "VEHICLE OPERATION LOCKED OUT" in res.json()["detail"]


def test_driver_session_token_authorization(test_setup):
    """
    Test that a session can be retrieved and operated on using ?token=<session_token>,
    even if the client has a mismatched owner or is an in-cab driver device.
    """
    client, conn, driver_id, vehicle_id, _ = test_setup
    m_repo = MonitoringRepository(conn)

    session_id = m_repo.create_session(driver_id, vehicle_id, owner_id=999)
    session = m_repo.get_session(session_id)
    token = session.session_token

    # 1. Fetching with valid token succeeds even though test_owner has owner_id != 999
    res = client.get(f"/sessions/{session_id}?token={token}")
    assert res.status_code == 200
    assert res.json()["session_id"] == session_id

    # 2. Fetching with invalid token returns 403
    res_bad = client.get(f"/sessions/{session_id}?token=bad-token")
    assert res_bad.status_code == 403

    # 3. Pausing with valid token succeeds
    res_pause = client.post(f"/sessions/{session_id}/pause?token={token}")
    assert res_pause.status_code == 200
    assert res_pause.json()["is_paused"] is True

    # 4. Resuming with valid token succeeds
    res_resume = client.post(f"/sessions/{session_id}/resume?token={token}")
    assert res_resume.status_code == 200
    assert res_resume.json()["is_paused"] is False

    # 5. Ending with valid token succeeds
    res_end = client.delete(f"/sessions/{session_id}?token={token}")
    assert res_end.status_code == 200

