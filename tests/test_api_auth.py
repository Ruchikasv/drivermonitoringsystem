"""
Tests for Driver Facial Authentication API (/auth/register, /auth/authenticate).
"""

import sqlite3
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api.main import app
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.database.vehicle_repository import VehicleRepository
from app.face_recognition.detector import DetectedFace


@pytest.fixture
def client():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    d_repo = DriverRepository(conn)
    # Register a test driver with known embedding
    base_emb = np.zeros(512, dtype=np.float32)
    base_emb[0] = 1.0  # Unit vector pointing along axis 0
    d_id = d_repo.add_driver(name="Ruchika", embedding=base_emb, license_no="DL-KA-01-9988")

    v_repo = VehicleRepository(conn)
    v_id = v_repo.add_vehicle(registration_number="KA-01-MJ-8821", model="Tata Prima 4028.S", vehicle_type="Heavy Haul")
    v_repo.assign_vehicle(driver_id=d_id, vehicle_id=v_id)

    def _override_get_conn():
        return conn

    from app.api.auth import _get_db
    def _override_get_db():
        yield conn

    app.dependency_overrides[get_connection] = _override_get_conn
    app.dependency_overrides[_get_db] = _override_get_db

    test_client = TestClient(app)
    yield test_client, base_emb

    app.dependency_overrides.clear()
    conn.close()



def test_authenticate_success(client):
    test_client, base_emb = client

    # Mock the FaceDetector to return a face matching Ruchika's embedding
    mock_detector = MagicMock()
    mock_face = DetectedFace(
        bbox=np.array([10, 10, 100, 100]),
        score=0.99,
        embedding=base_emb,  # Exact match
    )
    mock_detector.detect_single_face.return_value = mock_face

    # Dummy base64 JPEG
    import cv2
    import base64
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)
    b64_str = base64.b64encode(buf).decode("utf-8")

    with patch("app.api.auth._get_detector", return_value=mock_detector):
        res = test_client.post("/auth/authenticate", json={"frame_b64": b64_str})
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Ruchika"
        assert data["vehicle_registration"] == "KA-01-MJ-8821"
        assert data["similarity"] >= 0.99


def test_authenticate_unrecognized_face(client):
    test_client, _ = client

    # Return an orthogonal embedding (similarity = 0.0)
    ortho_emb = np.zeros(512, dtype=np.float32)
    ortho_emb[1] = 1.0

    mock_detector = MagicMock()
    mock_detector.detect_single_face.return_value = DetectedFace(
        bbox=np.array([10, 10, 100, 100]),
        score=0.99,
        embedding=ortho_emb,
    )

    import cv2, base64
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)
    b64_str = base64.b64encode(buf).decode("utf-8")

    with patch("app.api.auth._get_detector", return_value=mock_detector):
        res = test_client.post("/auth/authenticate", json={"frame_b64": b64_str})
        assert res.status_code == 401
        assert "not recognised" in res.json()["detail"]
