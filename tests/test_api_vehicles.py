"""
API Integration tests for Vehicle Management Endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.database.vehicle_repository import VehicleRepository
from tests.test_database import _random_embedding


@pytest.fixture
def api_client(monkeypatch):
    """Yield a TestClient backed by an isolated in-memory database."""
    conn = get_connection(db_path=":memory:")
    init_db(conn)

    # For safety in API routes that call conn.close(), create a proxy
    class UncloseableConn:
        def __init__(self, c):
            self._c = c
        def __getattr__(self, name):
            return getattr(self._c, name)
        def close(self):
            pass

    uncloseable = UncloseableConn(conn)
    monkeypatch.setattr("app.api.vehicles.get_connection", lambda: uncloseable)
    monkeypatch.setattr("app.api.drivers.get_connection", lambda: uncloseable)
    app.dependency_overrides[get_connection] = lambda: uncloseable

    client = TestClient(app)
    yield client, conn
    app.dependency_overrides.pop(get_connection, None)
    conn.close()


class TestVehicleAPIEndpoints:
    """End-to-end FastAPI endpoint tests for Vehicle Management."""

    def test_get_vehicles_empty(self, api_client):
        client, _ = api_client
        res = client.get("/vehicles")
        assert res.status_code == 200
        assert res.json() == []

    def test_create_and_get_vehicle(self, api_client):
        client, _ = api_client
        payload = {
            "registration_number": "KA-04-E-4412",
            "model": "Ashok Leyland 2820",
            "vehicle_type": "Heavy Haul",
        }
        res = client.post("/vehicles", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["registration_number"] == "KA-04-E-4412"
        assert data["model"] == "Ashok Leyland 2820"
        assert data["vehicle_type"] == "Heavy Haul"

        # List vehicles
        res_list = client.get("/vehicles")
        assert res_list.status_code == 200
        vehicles = res_list.json()
        assert len(vehicles) == 1
        assert vehicles[0]["registration_number"] == "KA-04-E-4412"
        assert vehicles[0]["assigned_driver"] is None

    def test_update_vehicle(self, api_client):
        client, _ = api_client
        create_res = client.post(
            "/vehicles",
            json={
                "registration_number": "KA-51-AB-1904",
                "model": "BharatBenz 3528C",
                "vehicle_type": "Heavy Haul",
            },
        )
        v_id = create_res.json()["vehicle_id"]

        update_res = client.put(
            f"/vehicles/{v_id}",
            json={
                "registration_number": "KA-51-AB-1904-UPDATED",
                "model": "BharatBenz 3528C Pro",
                "vehicle_type": "Tipper",
            },
        )
        assert update_res.status_code == 200
        data = update_res.json()
        assert data["registration_number"] == "KA-51-AB-1904-UPDATED"
        assert data["model"] == "BharatBenz 3528C Pro"
        assert data["vehicle_type"] == "Tipper"

    def test_assign_and_unassign_vehicle_workflow(self, api_client):
        client, conn = api_client
        driver_repo = DriverRepository(conn)
        d_id = driver_repo.add_driver("Lakshmi", _random_embedding())

        v_res = client.post(
            "/vehicles",
            json={
                "registration_number": "KA-01-MJ-8821",
                "model": "Tata Prima 4028.S",
                "vehicle_type": "Heavy Haul",
            },
        )
        v_id = v_res.json()["vehicle_id"]

        # Assign vehicle
        assign_res = client.post(
            f"/drivers/{d_id}/vehicle",
            json={"vehicle_id": v_id},
        )
        assert assign_res.status_code == 200

        # Verify assigned driver metadata in GET /vehicles
        v_list = client.get("/vehicles").json()
        assert len(v_list) == 1
        assert v_list[0]["assigned_driver"]["driver_id"] == d_id
        assert v_list[0]["assigned_driver"]["name"] == "Lakshmi"

        # Deleting assigned vehicle safely unassigns it and deletes the vehicle
        del_res = client.delete(f"/vehicles/{v_id}")
        assert del_res.status_code == 200
        assert len(client.get("/vehicles").json()) == 0

        # Driver remains registered in /drivers
        drivers = client.get("/drivers").json()
        assert any(d["driver_id"] == d_id for d in drivers)

    def test_delete_actively_used_vehicle_returns_409(self, api_client):
        client, conn = api_client
        driver_repo = DriverRepository(conn)
        d_id = driver_repo.add_driver("ActiveRuchika", _random_embedding())

        v_res = client.post(
            "/vehicles",
            json={
                "registration_number": "KA-01-LIVE-TRIP",
                "model": "Tata Signa",
                "vehicle_type": "Heavy Haul",
            },
        )
        v_id = v_res.json()["vehicle_id"]

        # Create ACTIVE monitoring session
        from app.database.monitoring_repository import MonitoringRepository
        m_repo = MonitoringRepository(conn)
        session_id = m_repo.create_session(driver_id=d_id, vehicle_id=v_id)

        # Attempt to delete vehicle while session is active -> 409 Conflict
        del_res = client.delete(f"/vehicles/{v_id}")
        assert del_res.status_code == 409
        assert "currently active on route" in del_res.json()["detail"]

        # End session -> Deletion now succeeds
        m_repo.end_session(session_id, status="COMPLETED")
        del_success = client.delete(f"/vehicles/{v_id}")
        assert del_success.status_code == 200
        assert len(client.get("/vehicles").json()) == 0

    def test_delete_nonexistent_vehicle_returns_404(self, api_client):
        client, _ = api_client
        res = client.delete("/vehicles/999999")
        assert res.status_code == 404

    def test_delete_vehicle_with_historical_monitoring_sessions_foreign_key_safety(self, api_client):
        client, conn = api_client
        driver_repo = DriverRepository(conn)
        d_id = driver_repo.add_driver("Arjun", _random_embedding())

        # 1. Create a vehicle
        v_res = client.post(
            "/vehicles",
            json={
                "registration_number": "KA-53-M-9999",
                "model": "Volvo FH16",
                "vehicle_type": "Heavy Haul",
            },
        )
        v_id = v_res.json()["vehicle_id"]

        # 2. Assign and create a monitoring session with incidents referencing this vehicle
        from app.database.monitoring_repository import MonitoringRepository
        m_repo = MonitoringRepository(conn)
        session_id = m_repo.create_session(driver_id=d_id, vehicle_id=v_id)
        m_repo.create_incident(
            session_id=session_id,
            driver_id=d_id,
            vehicle_id=v_id,
            event_type="yawn",
            alert_level=1,
            kss_score=5.0,
            ear=0.25,
            mar=0.60,
            perclos=0.10,
            head_pitch_deg=0.0,
        )
        m_repo.end_session(session_id, status="COMPLETED")

        # 3. Deleting vehicle must succeed without sqlite3.IntegrityError: FOREIGN KEY constraint failed
        del_res = client.delete(f"/vehicles/{v_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

        # 4. Immediate GET /vehicles must not contain the deleted vehicle
        vehicles = client.get("/vehicles").json()
        assert not any(v["vehicle_id"] == v_id for v in vehicles)

        # 5. Session and incident records must still exist with vehicle_id set to NULL
        session_record = m_repo.get_session(session_id)
        assert session_record is not None
        assert session_record.vehicle_id is None


