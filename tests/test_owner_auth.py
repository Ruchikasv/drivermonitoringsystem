"""
Unit & Integration Tests for Step 2 Owner Authentication, Multi-Tenancy Isolation, and Biometric Privacy.
"""

import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.owner_repository import OwnerRepository
from app.database.vehicle_repository import VehicleRepository


@pytest.fixture
def test_db():
    """Provides an in-memory SQLite database connection with full schema."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(test_db):
    """FastAPI TestClient overriding the get_connection dependency."""
    class UncloseableConn:
        def __init__(self, c):
            self._c = c
        def __getattr__(self, name):
            return getattr(self._c, name)
        def close(self):
            pass

    uncloseable = UncloseableConn(test_db)
    app.dependency_overrides[get_connection] = lambda: uncloseable
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()



# ===========================================================================
# 1. OWNER REGISTRATION & LOGIN TESTS
# ===========================================================================

class TestOwnerAuth:
    def test_owner_registration_success(self, client):
        payload = {
            "name": "Acme Logistics",
            "email": "manager@acme.com",
            "password": "SecurePassword123!",
        }
        res = client.post("/owner/auth/register", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["owner_id"] is not None
        assert data["name"] == "Acme Logistics"
        assert data["email"] == "manager@acme.com"
        assert "token" in data
        # Check that password is never returned
        assert "password" not in data
        assert "password_hash" not in data
        # Check HttpOnly cookie set
        assert settings.COOKIE_NAME in res.cookies

    def test_owner_registration_duplicate_email(self, client):
        payload = {
            "name": "First Owner",
            "email": "duplicate@fleet.com",
            "password": "Password123!",
        }
        res1 = client.post("/owner/auth/register", json=payload)
        assert res1.status_code == 201

        res2 = client.post("/owner/auth/register", json=payload)
        assert res2.status_code == 409
        assert "already exists" in res2.json()["detail"]

    def test_owner_registration_invalid_password(self, client):
        payload = {
            "name": "Short Pass",
            "email": "short@fleet.com",
            "password": "short",  # < 8 chars
        }
        res = client.post("/owner/auth/register", json=payload)
        assert res.status_code == 422

    def test_owner_count_endpoint(self, client):
        # Initial count
        c1 = client.get("/owner/auth/count").json()["count"]

        # Register owner 1
        client.post(
            "/owner/auth/register",
            json={"name": "Owner Counter 1", "email": "cnt1@fleet.com", "password": "Password123!"},
        )
        c2 = client.get("/owner/auth/count").json()["count"]
        assert c2 == c1 + 1

        # Register owner 2
        client.post(
            "/owner/auth/register",
            json={"name": "Owner Counter 2", "email": "cnt2@fleet.com", "password": "Password123!"},
        )
        c3 = client.get("/owner/auth/count").json()["count"]
        assert c3 == c1 + 2

    def test_owner_login_success_and_logout(self, client):
        # 1. Register
        client.post(
            "/owner/auth/register",
            json={"name": "Fleet Corp", "email": "admin@fleetcorp.com", "password": "StrongPassword888"},
        )

        # 2. Login
        login_res = client.post(
            "/owner/auth/login",
            json={"email": "admin@fleetcorp.com", "password": "StrongPassword888"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        assert token is not None

        # 3. Access /owner/auth/me with Bearer token
        me_res = client.get("/owner/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "admin@fleetcorp.com"

        # 4. Logout
        logout_res = client.post("/owner/auth/logout")
        assert logout_res.status_code == 200

    def test_owner_login_invalid_credentials(self, client):
        client.post(
            "/owner/auth/register",
            json={"name": "Owner X", "email": "x@fleet.com", "password": "Password123!"},
        )
        bad_login = client.post(
            "/owner/auth/login",
            json={"email": "x@fleet.com", "password": "WrongPassword!"},
        )
        assert bad_login.status_code == 401


# ===========================================================================
# 2. ROUTE PROTECTION & MULTI-TENANT FLEET ISOLATION
# ===========================================================================

class TestMultiTenantIsolation:
    def test_unauthenticated_requests_blocked(self, client):
        # Protected endpoints should return 401 without auth
        assert client.get("/drivers").status_code == 401
        assert client.get("/vehicles").status_code == 401
        assert client.get("/incidents/").status_code == 401
        assert client.get("/trips").status_code == 401
        assert client.get("/alerts").status_code == 401
        assert client.get("/analytics/metrics").status_code == 401

    def test_tenant_data_isolation_comprehensive(self, client, test_db):
        import numpy as np

        d_repo = DriverRepository(test_db)
        m_repo = MonitoringRepository(test_db)

        # 1. Register Owner A
        res_a = client.post(
            "/owner/auth/register",
            json={"name": "Owner Alpha", "email": "alpha@fleet.com", "password": "PasswordAlpha123!"},
        )
        assert res_a.status_code == 201
        token_a = res_a.json()["token"]
        owner_a_id = res_a.json()["owner_id"]
        auth_a = {"Authorization": f"Bearer {token_a}"}

        # 2. Register Owner B
        res_b = client.post(
            "/owner/auth/register",
            json={"name": "Owner Beta", "email": "beta@fleet.com", "password": "PasswordBeta123!"},
        )
        assert res_b.status_code == 201
        token_b = res_b.json()["token"]
        owner_b_id = res_b.json()["owner_id"]
        auth_b = {"Authorization": f"Bearer {token_b}"}

        # 3. Create Driver A and Driver B via DriverRepository with respective owner_ids
        driver_a_id = d_repo.add_driver(
            name="Driver Alpha One",
            embedding=np.random.randn(512).astype(np.float32),
            license_no="LIC-ALPHA-01",
            owner_id=owner_a_id,
        )
        driver_b_id = d_repo.add_driver(
            name="Driver Beta One",
            embedding=np.random.randn(512).astype(np.float32),
            license_no="LIC-BETA-01",
            owner_id=owner_b_id,
        )

        # 4. Create Vehicle A and Vehicle B via API
        v_res_a = client.post(
            "/vehicles",
            headers=auth_a,
            json={"registration_number": "KA-01-ALPHA", "model": "Tata Prima", "vehicle_type": "Heavy Truck"},
        )
        assert v_res_a.status_code == 200
        veh_a_id = v_res_a.json()["vehicle_id"]

        v_res_b = client.post(
            "/vehicles",
            headers=auth_b,
            json={"registration_number": "MH-02-BETA", "model": "Volvo FH16", "vehicle_type": "Trailer"},
        )
        assert v_res_b.status_code == 200
        veh_b_id = v_res_b.json()["vehicle_id"]

        # 5. Verify Driver List Isolation
        drivers_a = client.get("/drivers", headers=auth_a).json()
        drivers_b = client.get("/drivers", headers=auth_b).json()
        assert len(drivers_a) == 1
        assert drivers_a[0]["driver_id"] == driver_a_id
        assert drivers_a[0]["name"] == "Driver Alpha One"
        assert len(drivers_b) == 1
        assert drivers_b[0]["driver_id"] == driver_b_id
        assert drivers_b[0]["name"] == "Driver Beta One"

        # 6. Verify Single Driver GET/PUT/DELETE Isolation (Cross-access returns 404)
        assert client.get(f"/drivers/{driver_b_id}", headers=auth_a).status_code == 404
        assert client.get(f"/drivers/{driver_a_id}", headers=auth_b).status_code == 404

        assert client.put(
            f"/drivers/{driver_b_id}/profile",
            headers=auth_a,
            json={"name": "Hacked Name"},
        ).status_code == 404

        assert client.delete(f"/drivers/{driver_b_id}", headers=auth_a).status_code == 404

        # 7. Verify Vehicle List Isolation
        vehicles_a = client.get("/vehicles", headers=auth_a).json()
        vehicles_b = client.get("/vehicles", headers=auth_b).json()
        assert len(vehicles_a) == 1
        assert vehicles_a[0]["registration_number"] == "KA-01-ALPHA"
        assert len(vehicles_b) == 1
        assert vehicles_b[0]["registration_number"] == "MH-02-BETA"

        # 8. Verify Single Vehicle GET/PUT/DELETE Isolation (Cross-access returns 404)
        assert client.get(f"/vehicles/{veh_b_id}", headers=auth_a).status_code == 404
        assert client.get(f"/vehicles/{veh_a_id}", headers=auth_b).status_code == 404

        assert client.put(
            f"/vehicles/{veh_b_id}",
            headers=auth_a,
            json={"registration_number": "KA-01-ALPHA-EDIT", "model": "Tata New", "vehicle_type": "Truck"},
        ).status_code == 404

        assert client.delete(f"/vehicles/{veh_b_id}", headers=auth_a).status_code == 404

        # 9. Verify Cross-Tenant Vehicle Assignment Blocked
        # Owner A cannot assign Driver A to Vehicle B
        assign_bad_1 = client.post(
            f"/drivers/{driver_a_id}/vehicle",
            headers=auth_a,
            json={"vehicle_id": veh_b_id},
        )
        assert assign_bad_1.status_code == 404

        # Owner A cannot assign Driver B to Vehicle A
        assign_bad_2 = client.post(
            f"/drivers/{driver_b_id}/vehicle",
            headers=auth_a,
            json={"vehicle_id": veh_a_id},
        )
        assert assign_bad_2.status_code == 404

        # Owner A assigns Driver A to Vehicle A successfully
        assign_ok_a = client.post(
            f"/drivers/{driver_a_id}/vehicle",
            headers=auth_a,
            json={"vehicle_id": veh_a_id},
        )
        assert assign_ok_a.status_code == 200

        # Owner B assigns Driver B to Vehicle B successfully
        assign_ok_b = client.post(
            f"/drivers/{driver_b_id}/vehicle",
            headers=auth_b,
            json={"vehicle_id": veh_b_id},
        )
        assert assign_ok_b.status_code == 200

        # 10. Create Monitoring Sessions and Incidents for each owner
        sess_a_id = m_repo.create_session(driver_id=driver_a_id, vehicle_id=veh_a_id, owner_id=owner_a_id)
        inc_a_id = m_repo.create_incident(
            session_id=sess_a_id,
            driver_id=driver_a_id,
            vehicle_id=veh_a_id,
            owner_id=owner_a_id,
            event_type="critical",
            alert_level=3,
            kss_score=8.0,
            ear=0.14,
            evidence_path="data/evidence/test_alpha.jpg",
        )

        sess_b_id = m_repo.create_session(driver_id=driver_b_id, vehicle_id=veh_b_id, owner_id=owner_b_id)
        inc_b_id = m_repo.create_incident(
            session_id=sess_b_id,
            driver_id=driver_b_id,
            vehicle_id=veh_b_id,
            owner_id=owner_b_id,
            event_type="warning",
            alert_level=2,
            kss_score=6.5,
            ear=0.18,
            evidence_path="data/evidence/test_beta.jpg",
        )

        # 11. Verify Incidents and Evidence Isolation (Cross-access returns 404)
        inc_list_a = client.get("/incidents/", headers=auth_a).json()
        assert len(inc_list_a) == 1
        assert inc_list_a[0]["incident_id"] == inc_a_id

        inc_list_b = client.get("/incidents/", headers=auth_b).json()
        assert len(inc_list_b) == 1
        assert inc_list_b[0]["incident_id"] == inc_b_id

        assert client.get(f"/incidents/{inc_b_id}", headers=auth_a).status_code == 404
        assert client.get(f"/incidents/{inc_a_id}", headers=auth_b).status_code == 404

        assert client.get(f"/incidents/{inc_b_id}/evidence", headers=auth_a).status_code == 404
        assert client.delete(f"/incidents/{inc_b_id}/evidence", headers=auth_a).status_code == 404

        # 12. Verify Trips Isolation and Search Isolation
        trips_a = client.get("/trips", headers=auth_a).json()
        assert len(trips_a) == 1
        assert trips_a[0]["session_id"] == sess_a_id
        assert trips_a[0]["driver_name"] == "Driver Alpha One"

        trips_b = client.get("/trips", headers=auth_b).json()
        assert len(trips_b) == 1
        assert trips_b[0]["session_id"] == sess_b_id
        assert trips_b[0]["driver_name"] == "Driver Beta One"

        # Searching for Alpha's driver from Beta's account returns empty list
        search_cross = client.get("/trips?search=Alpha", headers=auth_b).json()
        assert len(search_cross) == 0

        # 13. Verify Alerts Isolation
        alerts_a = client.get("/alerts", headers=auth_a).json()
        assert len(alerts_a) == 1
        assert alerts_a[0]["incident_id"] == inc_a_id

        alerts_b = client.get("/alerts", headers=auth_b).json()
        assert len(alerts_b) == 1
        assert alerts_b[0]["incident_id"] == inc_b_id

        # 14. Verify Analytics Isolation
        metrics_a = client.get("/analytics/metrics", headers=auth_a).json()
        metrics_b = client.get("/analytics/metrics", headers=auth_b).json()
        assert metrics_a["total_drivers"] == 1
        assert metrics_a["total_incidents"] == 1
        assert metrics_a["critical_incidents"] == 1
        assert metrics_a["warning_incidents"] == 0

        assert metrics_b["total_drivers"] == 1
        assert metrics_b["total_incidents"] == 1
        assert metrics_b["critical_incidents"] == 0
        assert metrics_b["warning_incidents"] == 1

        alerts_by_driver_a = client.get("/analytics/alerts-by-driver", headers=auth_a).json()
        assert len(alerts_by_driver_a) == 1
        assert alerts_by_driver_a[0]["name"] == "Driver Alpha One"

        alerts_by_driver_b = client.get("/analytics/alerts-by-driver", headers=auth_b).json()
        assert len(alerts_by_driver_b) == 1
        assert alerts_by_driver_b[0]["name"] == "Driver Beta One"


# ===========================================================================
# 3. BIOMETRIC PRIVACY & DRIVER DELETION
# ===========================================================================

class TestBiometricPrivacyOnDriverDeletion:
    def test_fire_driver_zeroes_embedding_and_preserves_audit_logs(self, test_db):
        import numpy as np

        d_repo = DriverRepository(test_db)
        m_repo = MonitoringRepository(test_db)
        v_repo = VehicleRepository(test_db)

        # 1. Register driver with biometric embedding
        fake_emb = np.random.randn(512).astype(np.float32)
        driver_id = d_repo.add_driver(name="John Doe", embedding=fake_emb, license_no="DL-12345")
        assert driver_id > 0

        # 2. Add vehicle and create a monitoring session
        vehicle_id = v_repo.add_vehicle(registration_number="KA-05-MH-9999", model="Ashok Leyland", vehicle_type="Truck")
        session_id = m_repo.create_session(driver_id=driver_id, vehicle_id=vehicle_id)

        # Record an incident
        inc_id = m_repo.create_incident(
            session_id=session_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            event_type="critical",
            alert_level=3,
            kss_score=8.5,
            ear=0.15,
            mar=0.35,
            perclos=0.45,
        )
        assert inc_id > 0

        # 3. Fire / delete driver
        deleted = d_repo.delete_driver(driver_id)
        assert deleted is True

        # 4. Check that driver is no longer in active fleet
        active_drivers = d_repo.get_all_drivers()
        assert not any(d.driver_id == driver_id for d in active_drivers)

        # 5. Check that biometric face_embedding is completely wiped (NULL)
        row = test_db.execute("SELECT face_embedding, is_active, deleted_at FROM drivers WHERE driver_id = ?", (driver_id,)).fetchone()
        assert row["face_embedding"] is None
        assert row["is_active"] == 0
        assert row["deleted_at"] is not None

        # 6. Check that historical session and incident audit logs are preserved
        sess = m_repo.get_session(session_id)
        assert sess is not None
        assert sess.status == "INTERRUPTED"

        inc = m_repo.get_incident(inc_id)
        assert inc is not None
        assert inc.alert_level == 3
        assert inc.kss_score == 8.5


# ===========================================================================
# 4. TENANT-SCOPED BIOMETRIC REGISTRATION & DUPLICATE CHECKS
# ===========================================================================

class TestTenantScopedBiometricRegistration:
    def test_same_driver_registered_across_multiple_owners(self, client):
        import base64
        import cv2
        import numpy as np
        from unittest.mock import MagicMock, patch
        from app.face_recognition.detector import DetectedFace

        # Dummy face embedding representing "Ruchika"
        ruchika_emb = np.zeros(512, dtype=np.float32)
        ruchika_emb[0] = 1.0

        mock_detector = MagicMock()
        mock_detector.detect_single_face.return_value = DetectedFace(
            bbox=np.array([10, 10, 100, 100]),
            score=0.99,
            embedding=ruchika_emb,
        )

        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", dummy_img)
        b64_frame = base64.b64encode(buf).decode("utf-8")

        # 1. Register Owner A and Owner B
        res_a = client.post(
            "/owner/auth/register",
            json={"name": "Owner A Logistics", "email": "ownera@multitenant.com", "password": "Password123!"},
        )
        token_a = res_a.json()["token"]
        auth_a = {"Authorization": f"Bearer {token_a}"}

        res_b = client.post(
            "/owner/auth/register",
            json={"name": "Owner B Transport", "email": "ownerb@multitenant.com", "password": "Password123!"},
        )
        token_b = res_b.json()["token"]
        auth_b = {"Authorization": f"Bearer {token_b}"}

        reg_payload = {
            "name": "Ruchika",
            "phone": "+91 99999 11111",
            "email": "ruchika@driver.com",
            "license_no": "DL-KA-RUCHIKA-01",
            "frames_b64": [b64_frame, b64_frame, b64_frame],
        }

        with patch("app.api.auth._get_detector", return_value=mock_detector):
            # 2. Owner A registers Ruchika -> SUCCESS
            reg_res_a = client.post("/auth/register", headers=auth_a, json=reg_payload)
            assert reg_res_a.status_code == 201
            driver_a_id = reg_res_a.json()["driver_id"]
            assert driver_a_id > 0

            # 3. Owner B registers Ruchika using the exact SAME face biometrics -> SUCCESS
            reg_res_b = client.post("/auth/register", headers=auth_b, json=reg_payload)
            assert reg_res_b.status_code == 201
            driver_b_id = reg_res_b.json()["driver_id"]
            assert driver_b_id > 0
            assert driver_b_id != driver_a_id

            # 4. Owner A attempts to register Ruchika AGAIN -> 409 Duplicate Error
            dup_res_a = client.post("/auth/register", headers=auth_a, json=reg_payload)
            assert dup_res_a.status_code == 409
            assert "already registered with matching facial biometrics" in dup_res_a.json()["detail"] or "Driving license" in dup_res_a.json()["detail"]

            # 5. Owner B attempts to register Ruchika AGAIN -> 409 Duplicate Error
            dup_res_b = client.post("/auth/register", headers=auth_b, json=reg_payload)
            assert dup_res_b.status_code == 409
            assert "already registered with matching facial biometrics" in dup_res_b.json()["detail"] or "Driving license" in dup_res_b.json()["detail"]

            # 6. Owner A sees only Owner A's copy of Ruchika
            drivers_a = client.get("/drivers", headers=auth_a).json()
            assert len(drivers_a) == 1
            assert drivers_a[0]["driver_id"] == driver_a_id
            assert client.get(f"/drivers/{driver_b_id}", headers=auth_a).status_code == 404

            # 7. Owner B sees only Owner B's copy of Ruchika
            drivers_b = client.get("/drivers", headers=auth_b).json()
            assert len(drivers_b) == 1
            assert drivers_b[0]["driver_id"] == driver_b_id
            assert client.get(f"/drivers/{driver_a_id}", headers=auth_b).status_code == 404

            # 8. Unauthenticated Driver Cab Portal authentication succeeds
            auth_res = client.post("/auth/authenticate", json={"frame_b64": b64_frame})
            assert auth_res.status_code == 200
            auth_data = auth_res.json()
            assert auth_data["name"] == "Ruchika"
            assert auth_data["driver_id"] in (driver_a_id, driver_b_id)
            assert auth_data["session_id"] is not None
            assert auth_data["session_token"] is not None

    def test_dynamic_fleet_safety_score_consistency_and_zero_data(self, client, test_db):
        import numpy as np

        d_repo = DriverRepository(test_db)
        m_repo = MonitoringRepository(test_db)
        v_repo = VehicleRepository(test_db)

        # 1. Register Owner A (0 drivers)
        res_a = client.post(
            "/owner/auth/register",
            json={"name": "Owner Zero", "email": "zero@safety.com", "password": "Password123!"},
        )
        token_a = res_a.json()["token"]
        owner_a_id = res_a.json()["owner_id"]
        auth_a = {"Authorization": f"Bearer {token_a}"}

        # 2. Check metrics for 0-driver fleet
        metrics_0 = client.get("/analytics/metrics", headers=auth_a).json()
        assert metrics_0["total_drivers"] == 0
        assert metrics_0["totalDrivers"] == 0
        assert metrics_0["fleetSafetyScore"] is None
        assert metrics_0["average_safety_score"] is None

        # Check score distribution for 0-driver fleet is empty
        dist_0 = client.get("/analytics/score-distribution", headers=auth_a).json()
        assert len(dist_0) == 0

        # 3. Add Driver 1 for Owner A (0 sessions -> pristine 100% baseline)
        d1_id = d_repo.add_driver(
            name="Driver Safe",
            embedding=np.random.randn(512).astype(np.float32),
            license_no="LIC-SAFE-01",
            owner_id=owner_a_id,
        )
        metrics_1 = client.get("/analytics/metrics", headers=auth_a).json()
        assert metrics_1["total_drivers"] == 1
        assert metrics_1["fleetSafetyScore"] == 100.0
        assert metrics_1["average_safety_score"] == 100.0

        # 4. Create a session and record 1 critical incident (100 - 8 = 92.0)
        v_id = v_repo.add_vehicle(registration_number="KA-01-SAFE", model="Tata", vehicle_type="Truck", owner_id=owner_a_id)
        s_id = m_repo.create_session(driver_id=d1_id, vehicle_id=v_id, owner_id=owner_a_id)
        m_repo.create_incident(
            session_id=s_id,
            driver_id=d1_id,
            vehicle_id=v_id,
            owner_id=owner_a_id,
            event_type="critical",
            alert_level=3,
            kss_score=8.5,
        )
        m_repo.end_session(s_id, status="COMPLETED")
        m_repo.recalculate_safety_rating(d1_id)

        # 5. Verify dynamic calculation: fleet safety score is exactly 92.0
        metrics_2 = client.get("/analytics/metrics", headers=auth_a).json()
        assert metrics_2["fleetSafetyScore"] == 92.0
        assert metrics_2["average_safety_score"] == 92.0

        # 6. Register Owner B with 0 drivers -> Owner B still gets clean zero-data state (None), not Owner A's 92.0
        res_b = client.post(
            "/owner/auth/register",
            json={"name": "Owner Other", "email": "other@safety.com", "password": "Password123!"},
        )
        token_b = res_b.json()["token"]
        auth_b = {"Authorization": f"Bearer {token_b}"}

        metrics_b = client.get("/analytics/metrics", headers=auth_b).json()
        assert metrics_b["total_drivers"] == 0
        assert metrics_b["fleetSafetyScore"] is None

    def test_evidence_lifecycle_preservation_and_deletion(self, client, test_db):
        import os
        import numpy as np

        d_repo = DriverRepository(test_db)
        m_repo = MonitoringRepository(test_db)
        v_repo = VehicleRepository(test_db)

        # 1. Register Owner A and Owner B
        res_a = client.post(
            "/owner/auth/register",
            json={"name": "Evidence Owner A", "email": "evidence_a@test.com", "password": "Password123!"},
        )
        token_a = res_a.json()["token"]
        owner_a_id = res_a.json()["owner_id"]
        auth_a = {"Authorization": f"Bearer {token_a}"}

        res_b = client.post(
            "/owner/auth/register",
            json={"name": "Evidence Owner B", "email": "evidence_b@test.com", "password": "Password123!"},
        )
        token_b = res_b.json()["token"]
        auth_b = {"Authorization": f"Bearer {token_b}"}

        d_id = d_repo.add_driver(name="Test Evidence Driver", embedding=np.random.randn(512).astype(np.float32), owner_id=owner_a_id)
        v_id = v_repo.add_vehicle(registration_number="KA-09-EVID-01", model="Truck", vehicle_type="Heavy", owner_id=owner_a_id)
        s_id = m_repo.create_session(driver_id=d_id, vehicle_id=v_id, owner_id=owner_a_id)

        # 2. Create physical evidence file in data/evidence
        evidence_dir = os.path.join(str(settings.PROJECT_ROOT), "data", "evidence")
        os.makedirs(evidence_dir, exist_ok=True)
        evidence_filename = f"test_lifecycle_evid_{d_id}_{s_id}.jpg"
        evidence_filepath = os.path.join(evidence_dir, evidence_filename)
        with open(evidence_filepath, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb")

        rel_path = f"data/evidence/{evidence_filename}"

        inc_id = m_repo.create_incident(
            session_id=s_id,
            driver_id=d_id,
            vehicle_id=v_id,
            owner_id=owner_a_id,
            event_type="critical",
            alert_level=3,
            kss_score=8.8,
            ear=0.12,
            mar=0.35,
            perclos=0.55,
            head_pitch_deg=-15.5,
            evidence_path=rel_path,
        )

        # 3. Verify evidence is listed and has_evidence is True
        inc_list = client.get("/incidents/", headers=auth_a).json()
        assert len(inc_list) == 1
        assert inc_list[0]["incident_id"] == inc_id
        assert inc_list[0]["has_evidence"] is True
        assert inc_list[0]["evidence_path"] == rel_path

        # 4. Verify Owner A can view/download evidence JPEG
        evid_res_a = client.get(f"/incidents/{inc_id}/evidence", headers=auth_a)
        assert evid_res_a.status_code == 200
        assert evid_res_a.headers["content-type"] == "image/jpeg"

        # 5. Verify Owner B cannot view Owner A's evidence (404)
        evid_res_b = client.get(f"/incidents/{inc_id}/evidence", headers=auth_b)
        assert evid_res_b.status_code == 404

        # 6. Explicitly delete evidence via DELETE /incidents/{incident_id}/evidence
        del_evid_res = client.delete(f"/incidents/{inc_id}/evidence", headers=auth_a)
        assert del_evid_res.status_code == 200
        assert del_evid_res.json()["status"] == "success"

        # 7. Verify physical file is deleted from disk
        assert not os.path.exists(evidence_filepath)

        # 8. Verify database incident audit record is preserved with numerical metrics
        inc_after = m_repo.get_incident(inc_id, owner_id=owner_a_id)
        assert inc_after is not None
        assert inc_after.alert_level == 3
        assert inc_after.event_type == "critical"
        assert inc_after.ear == 0.12
        assert inc_after.kss_score == 8.8
        assert inc_after.evidence_path is None

        # 9. Verify GET /incidents returns has_evidence: False
        inc_list_after = client.get("/incidents/", headers=auth_a).json()
        assert len(inc_list_after) == 1
        assert inc_list_after[0]["has_evidence"] is False
        assert inc_list_after[0]["evidence_path"] is None
