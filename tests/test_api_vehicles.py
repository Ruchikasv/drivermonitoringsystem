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

    # Monkeypatch get_connection so API endpoints use our test connection
    def override_get_connection():
        # Return a connection to the same memory database (or wrap)
        # Note: :memory: is per-connection in SQLite unless URI shared cache is used
        # We can patch get_connection to return conn without closing
        return conn

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

    client = TestClient(app)
    yield client, conn
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

        # Attempt to delete assigned vehicle (must be blocked with detail error)
        del_res = client.delete(f"/vehicles/{v_id}")
        assert del_res.status_code == 400
        assert "currently assigned" in del_res.json()["detail"]

        # Unassign vehicle
        unassign_res = client.delete(f"/drivers/{d_id}/vehicle")
        assert unassign_res.status_code == 200

        # Verify vehicle is now available
        v_list_after = client.get("/vehicles").json()
        assert v_list_after[0]["assigned_driver"] is None

        # Delete available vehicle
        del_success = client.delete(f"/vehicles/{v_id}")
        assert del_success.status_code == 200
        assert len(client.get("/vehicles").json()) == 0
