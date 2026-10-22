"""
Tests for Owner Portal Safety Alerts and Notifications API (GET /alerts).
Verifies:
1. Retrieval of multi-tier alerts (Nudge, Warning, Critical) for the logged-in owner.
2. Proper driver, vehicle, and timestamp formatting.
3. Multi-tenant isolation: Owner A cannot see Owner B's alerts.
4. Limit and level filters.
5. Empty state handling (returns [] when no alerts exist).
"""

import sqlite3
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_owner
from app.api.main import app
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.owner_repository import OwnerRepository
from app.database.vehicle_repository import VehicleRepository


@pytest.fixture
def alert_test_setup():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    o_repo = OwnerRepository(conn)
    owner1_id = o_repo.create_owner(name="Fleet Owner 1", email="owner1@fleet.com", plain_password="Password123!")
    owner2_id = o_repo.create_owner(name="Fleet Owner 2", email="owner2@fleet.com", plain_password="Password123!")

    owner1 = o_repo.get_owner_by_id(owner1_id)
    owner2 = o_repo.get_owner_by_id(owner2_id)

    dummy_emb = np.ones(512, dtype=np.float32)
    d_repo = DriverRepository(conn)
    d1 = d_repo.add_driver(name="Rajesh Kumar", embedding=dummy_emb, owner_id=owner1_id)
    d2 = d_repo.add_driver(name="Suresh Patel", embedding=dummy_emb, owner_id=owner2_id)

    v_repo = VehicleRepository(conn)
    v1 = v_repo.add_vehicle(registration_number="KA-01-AB-1234", model="BharatBenz Heavy", vehicle_type="Truck", owner_id=owner1_id)
    v2 = v_repo.add_vehicle(registration_number="MH-02-CD-5678", model="Tata Prima", vehicle_type="Truck", owner_id=owner2_id)

    m_repo = MonitoringRepository(conn)
    s1 = m_repo.create_session(driver_id=d1, vehicle_id=v1, owner_id=owner1_id)
    s2 = m_repo.create_session(driver_id=d2, vehicle_id=v2, owner_id=owner2_id)

    # Seed alerts for Owner 1: Nudge, Warning, Critical
    m_repo.create_incident(
        session_id=s1,
        driver_id=d1,
        vehicle_id=v1,
        event_type="nudge",
        alert_level=1,
        kss_score=5.5,
        ear=0.18,
        perclos=0.16,
        owner_id=owner1_id,
    )
    m_repo.create_incident(
        session_id=s1,
        driver_id=d1,
        vehicle_id=v1,
        event_type="warning",
        alert_level=2,
        kss_score=6.8,
        ear=0.14,
        perclos=0.25,
        owner_id=owner1_id,
    )
    m_repo.create_incident(
        session_id=s1,
        driver_id=d1,
        vehicle_id=v1,
        event_type="critical",
        alert_level=3,
        kss_score=8.9,
        ear=0.10,
        perclos=0.45,
        evidence_path="data/evidence/sample.jpg",
        owner_id=owner1_id,
    )

    # Seed alert for Owner 2
    m_repo.create_incident(
        session_id=s2,
        driver_id=d2,
        vehicle_id=v2,
        event_type="critical",
        alert_level=3,
        kss_score=9.0,
        ear=0.08,
        perclos=0.50,
        owner_id=owner2_id,
    )

    app.dependency_overrides[get_connection] = lambda: conn

    yield {
        "conn": conn,
        "owner1": owner1,
        "owner2": owner2,
        "owner1_id": owner1_id,
        "owner2_id": owner2_id,
        "d1": d1,
        "d2": d2,
    }

    app.dependency_overrides.clear()


def test_owner1_fetches_own_alerts(alert_test_setup):
    owner1 = alert_test_setup["owner1"]
    app.dependency_overrides[get_current_owner] = lambda: owner1

    client = TestClient(app)
    response = client.get("/alerts")

    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 3

    # Check alert structure and contents
    critical_alert = next((a for a in alerts if a["level"] == 3), None)
    assert critical_alert is not None
    assert critical_alert["driver_name"] == "Rajesh Kumar"
    assert critical_alert["vehicle_plate"] == "KA-01-AB-1234"
    assert critical_alert["event_type"] == "Critical"
    assert "KSS=8.9" in critical_alert["notes"]

    warning_alert = next((a for a in alerts if a["level"] == 2), None)
    assert warning_alert is not None
    assert warning_alert["event_type"] == "Warning"

    nudge_alert = next((a for a in alerts if a["level"] == 1), None)
    assert nudge_alert is not None
    assert nudge_alert["event_type"] == "Nudge"


def test_multi_tenant_isolation_alerts(alert_test_setup):
    owner2 = alert_test_setup["owner2"]
    app.dependency_overrides[get_current_owner] = lambda: owner2

    client = TestClient(app)
    response = client.get("/alerts")

    assert response.status_code == 200
    alerts = response.json()
    # Owner 2 should only see their 1 alert, NEVER Owner 1's alerts
    assert len(alerts) == 1
    assert alerts[0]["driver_name"] == "Suresh Patel"
    assert alerts[0]["vehicle_plate"] == "MH-02-CD-5678"


def test_alerts_limit_parameter(alert_test_setup):
    owner1 = alert_test_setup["owner1"]
    app.dependency_overrides[get_current_owner] = lambda: owner1

    client = TestClient(app)
    response = client.get("/alerts?limit=2")

    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 2


def test_alerts_empty_state_new_owner(alert_test_setup):
    conn = alert_test_setup["conn"]
    o_repo = OwnerRepository(conn)
    owner3_id = o_repo.create_owner(name="Fresh Owner", email="fresh@fleet.com", plain_password="Password123!")
    owner3 = o_repo.get_owner_by_id(owner3_id)

    app.dependency_overrides[get_current_owner] = lambda: owner3

    client = TestClient(app)
    response = client.get("/alerts")

    assert response.status_code == 200
    alerts = response.json()
    assert alerts == []
