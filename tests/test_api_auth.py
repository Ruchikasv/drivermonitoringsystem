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

    from app.api.dependencies import get_current_owner, get_optional_owner
    from app.database.owner_repository import OwnerRecord, OwnerRepository

    o_repo = OwnerRepository(conn)
    owner_id = o_repo.create_owner("Test Owner", "owner@auth.com", "Password123!")
    test_owner = o_repo.get_owner_by_id(owner_id)

    d_repo = DriverRepository(conn)
    # Register a test driver with known embedding
    base_emb = np.zeros(512, dtype=np.float32)
    base_emb[0] = 1.0  # Unit vector pointing along axis 0
    d_id = d_repo.add_driver(name="Ruchika", embedding=base_emb, license_no="DL-KA-01-9988", owner_id=owner_id)

    v_repo = VehicleRepository(conn)
    v_id = v_repo.add_vehicle(registration_number="KA-01-MJ-8821", model="Tata Prima 4028.S", vehicle_type="Heavy Haul", owner_id=owner_id)
    v_repo.assign_vehicle(driver_id=d_id, vehicle_id=v_id, owner_id=owner_id)

    from app.api.auth import _get_db

    app.dependency_overrides[get_connection] = lambda: conn
    app.dependency_overrides[_get_db] = lambda: conn
    app.dependency_overrides[get_current_owner] = lambda: test_owner
    app.dependency_overrides[get_optional_owner] = lambda: test_owner

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


def test_register_driver_success(client):
    test_client, _ = client

    # Unique embedding for new driver
    new_emb = np.zeros(512, dtype=np.float32)
    new_emb[2] = 1.0  # Orthogonal to base_emb

    mock_detector = MagicMock()
    mock_detector.detect_single_face.return_value = DetectedFace(
        bbox=np.array([10, 10, 100, 100]),
        score=0.98,
        embedding=new_emb,
    )

    import cv2, base64
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)
    b64_str = base64.b64encode(buf).decode("utf-8")

    payload = {
        "name": "Vikram Singh",
        "phone": "+91 98765 12345",
        "email": "vikram@fleet.com",
        "license_no": "DL-KA-05-2024",
        "frames_b64": [b64_str, b64_str, b64_str],
    }

    with patch("app.api.auth._get_detector", return_value=mock_detector):
        res = test_client.post("/auth/register", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Vikram Singh"
        assert data["driver_id"] > 0
        assert "registered successfully" in data["message"]

        # Confirm driver was persisted in database
        driver_res = test_client.get(f"/drivers/{data['driver_id']}")
        assert driver_res.status_code == 200
        driver_data = driver_res.json()
        assert driver_data["name"] == "Vikram Singh"
        assert driver_data["license_no"] == "DL-KA-05-2024"


def test_register_driver_duplicate_license(client):
    test_client, _ = client

    new_emb = np.zeros(512, dtype=np.float32)
    new_emb[3] = 1.0

    mock_detector = MagicMock()
    mock_detector.detect_single_face.return_value = DetectedFace(
        bbox=np.array([10, 10, 100, 100]),
        score=0.98,
        embedding=new_emb,
    )

    import cv2, base64
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)
    b64_str = base64.b64encode(buf).decode("utf-8")

    # Ruchika's license is DL-KA-01-9988 from fixture
    payload = {
        "name": "Another Driver",
        "license_no": "DL-KA-01-9988",
        "frames_b64": [b64_str],
    }

    with patch("app.api.auth._get_detector", return_value=mock_detector):
        res = test_client.post("/auth/register", json=payload)
        assert res.status_code == 409
        assert "already registered" in res.json()["detail"]


def test_register_driver_duplicate_biometrics(client):
    test_client, base_emb = client

    # Provide same embedding as Ruchika (similarity = 1.0 >= 0.55 threshold)
    mock_detector = MagicMock()
    mock_detector.detect_single_face.return_value = DetectedFace(
        bbox=np.array([10, 10, 100, 100]),
        score=0.98,
        embedding=base_emb,
    )

    import cv2, base64
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)
    b64_str = base64.b64encode(buf).decode("utf-8")

    payload = {
        "name": "Ruchika Clone",
        "license_no": "DL-NEW-9999",
        "frames_b64": [b64_str, b64_str],
    }

    with patch("app.api.auth._get_detector", return_value=mock_detector):
        res = test_client.post("/auth/register", json=payload)
        assert res.status_code == 409
        assert "matching facial biometrics" in res.json()["detail"]


def test_register_driver_no_face_detected(client):
    test_client, _ = client

    mock_detector = MagicMock()
    mock_detector.detect_single_face.return_value = None  # No face detected

    import cv2, base64
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)
    b64_str = base64.b64encode(buf).decode("utf-8")

    payload = {
        "name": "Invisible Driver",
        "frames_b64": [b64_str],
    }

    with patch("app.api.auth._get_detector", return_value=mock_detector):
        res = test_client.post("/auth/register", json=payload)
        assert res.status_code == 422
        assert "No face detected" in res.json()["detail"]


def test_system_health_and_service_unavailable():
    # Test system health reporting face recognition readiness
    test_client = TestClient(app)

    with patch("app.api.auth.is_model_ready", return_value=(True, None)):
        res = test_client.get("/system/health")
        assert res.status_code == 200
        data = res.json()
        assert data["services"]["face_recognition"] == "ready"
        assert data["status"] == "healthy"

    with patch("app.api.auth.is_model_ready", return_value=(False, "GPU out of memory")):
        res = test_client.get("/system/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "degraded"
        assert "error" in data["services"]["face_recognition"]


def test_auth_register_fails_with_503_if_model_fails():
    test_client = TestClient(app)
    import cv2, base64
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", dummy_img)
    b64_str = base64.b64encode(buf).decode("utf-8")

    payload = {
        "name": "Test Driver",
        "frames_b64": [b64_str],
    }

    with patch("app.api.auth.warmup_detector", return_value=False), \
         patch("app.api.auth._model_ready", False), \
         patch("app.api.auth._model_error", "Model weights file not found"):
        res = test_client.post("/auth/register", json=payload)
        assert res.status_code == 503
        assert "Face recognition service is unavailable" in res.json()["detail"]


def test_onnx_execution_providers_configuration():
    """Verify that FaceDetector configures only supported ONNX execution providers."""
    from app.face_recognition.detector import FaceDetector

    detector = FaceDetector()

    with patch("onnxruntime.get_available_providers", return_value=["AzureExecutionProvider", "CPUExecutionProvider"]), \
         patch("insightface.app.FaceAnalysis") as mock_fa:
        mock_instance = MagicMock()
        mock_fa.return_value = mock_instance

        detector._ensure_model_loaded()

        # FaceAnalysis must be called with providers=['CPUExecutionProvider'] (NO CUDA requested)
        mock_fa.assert_called_once()
        _, kwargs = mock_fa.call_args
        assert kwargs["providers"] == ["CPUExecutionProvider"]

    # When CUDA IS available, both CUDA and CPU should be passed
    detector2 = FaceDetector()
    with patch("onnxruntime.get_available_providers", return_value=["CUDAExecutionProvider", "CPUExecutionProvider"]), \
         patch("insightface.app.FaceAnalysis") as mock_fa2:
        mock_instance2 = MagicMock()
        mock_fa2.return_value = mock_instance2

        detector2._ensure_model_loaded()

        mock_fa2.assert_called_once()
        _, kwargs2 = mock_fa2.call_args
        assert kwargs2["providers"] == ["CUDAExecutionProvider", "CPUExecutionProvider"]


