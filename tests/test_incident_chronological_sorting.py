import sqlite3
import numpy as np
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_owner
from app.api.main import app
from app.database.connection import get_connection, init_db
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.owner_repository import OwnerRepository
from app.database.vehicle_repository import VehicleRepository


@pytest.fixture
def multi_driver_incidents_setup():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    o_repo = OwnerRepository(conn)
    owner_id = o_repo.create_owner(
        name="Global Fleet Owner",
        email="global_owner@fleet.com",
        plain_password="Password123!"
    )
    owner = o_repo.get_owner_by_id(owner_id)

    dummy_emb = np.ones(512, dtype=np.float32)
    d_repo = DriverRepository(conn)
    driver_alpha = d_repo.add_driver(name="Alpha Driver", embedding=dummy_emb, license_no="DL-ALPHA-01", owner_id=owner_id)
    driver_beta = d_repo.add_driver(name="Beta Driver", embedding=dummy_emb, license_no="DL-BETA-02", owner_id=owner_id)
    driver_gamma = d_repo.add_driver(name="Gamma Driver", embedding=dummy_emb, license_no="DL-GAMMA-03", owner_id=owner_id)

    v_repo = VehicleRepository(conn)
    v1 = v_repo.add_vehicle(registration_number="KA-01-AA-1111", model="Truck Alpha", vehicle_type="Truck", owner_id=owner_id)
    v2 = v_repo.add_vehicle(registration_number="KA-02-BB-2222", model="Truck Beta", vehicle_type="Truck", owner_id=owner_id)
    v3 = v_repo.add_vehicle(registration_number="KA-03-CC-3333", model="Truck Gamma", vehicle_type="Truck", owner_id=owner_id)

    m_repo = MonitoringRepository(conn)
    s1 = m_repo.create_session(driver_id=driver_alpha, vehicle_id=v1, owner_id=owner_id)
    s2 = m_repo.create_session(driver_id=driver_beta, vehicle_id=v2, owner_id=owner_id)
    s3 = m_repo.create_session(driver_id=driver_gamma, vehicle_id=v3, owner_id=owner_id)

    # Insert incidents at specific timestamps across different drivers
    # T0: Alpha Driver (earliest)
    # T1: Beta Driver
    # T2: Gamma Driver
    # T3: Alpha Driver
    # T4: Beta Driver (newest)
    base_time = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone.utc)
    t0 = (base_time + timedelta(minutes=0)).isoformat()
    t1 = (base_time + timedelta(minutes=10)).isoformat()
    t2 = (base_time + timedelta(minutes=20)).isoformat()
    t3 = (base_time + timedelta(minutes=30)).isoformat()
    t4 = (base_time + timedelta(minutes=40)).isoformat()

    # Direct insert to control exact occurrence timestamps
    inc_data = [
        (s1, driver_alpha, v1, owner_id, t0, "nudge", 1, 5.0, None, None, None, None, None, None, None),
        (s2, driver_beta, v2, owner_id, t1, "warning", 2, 6.5, None, None, None, None, None, None, None),
        (s3, driver_gamma, v3, owner_id, t2, "critical", 3, 8.5, None, None, None, None, None, None, None),
        (s1, driver_alpha, v1, owner_id, t3, "distraction", 2, 6.0, None, None, None, None, None, "Phone", 3.0),
        (s2, driver_beta, v2, owner_id, t4, "critical", 3, 9.0, None, None, None, None, None, None, None),
    ]

    for item in inc_data:
        conn.execute(
            """
            INSERT INTO monitoring_incidents
              (session_id, driver_id, vehicle_id, owner_id, timestamp, event_type, alert_level,
               kss_score, ear, mar, perclos, head_pitch_deg, evidence_path, distraction_type, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            item
        )
    conn.commit()

    app.dependency_overrides[get_connection] = lambda: conn
    app.dependency_overrides[get_current_owner] = lambda: owner

    client = TestClient(app)
    yield {
        "conn": conn,
        "m_repo": m_repo,
        "owner": owner,
        "owner_id": owner_id,
        "client": client,
        "driver_alpha": driver_alpha,
        "driver_beta": driver_beta,
        "driver_gamma": driver_gamma,
        "timestamps": [t4, t3, t2, t1, t0],
    }

    app.dependency_overrides.clear()
    conn.close()


def test_incidents_api_sorted_globally_newest_first_across_drivers(multi_driver_incidents_setup):
    """
    GET /incidents must return all incident records globally sorted by occurrence timestamp
    in descending order (newest first), NOT grouped or sorted by driver.
    """
    client = multi_driver_incidents_setup["client"]
    expected_order = multi_driver_incidents_setup["timestamps"]
    driver_alpha = multi_driver_incidents_setup["driver_alpha"]
    driver_beta = multi_driver_incidents_setup["driver_beta"]
    driver_gamma = multi_driver_incidents_setup["driver_gamma"]

    response = client.get("/incidents")
    assert response.status_code == 200
    incidents = response.json()
    assert len(incidents) == 5

    # Verify timestamps are strictly descending
    received_timestamps = [inc["timestamp"] for inc in incidents]
    assert received_timestamps == expected_order

    # Verify drivers alternate in true chronological order, NOT grouped by driver
    received_drivers = [inc["driver_id"] for inc in incidents]
    assert received_drivers == [
        driver_beta,   # T4 (newest)
        driver_alpha,  # T3
        driver_gamma,  # T2
        driver_beta,   # T1
        driver_alpha,  # T0 (oldest)
    ]


def test_alerts_api_sorted_globally_newest_first_across_drivers(multi_driver_incidents_setup):
    """
    GET /alerts must also return all alert records globally sorted newest first.
    """
    client = multi_driver_incidents_setup["client"]
    expected_order = multi_driver_incidents_setup["timestamps"]

    response = client.get("/alerts")
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 5

    received_timestamps = [alt["timestamp"] for alt in alerts]
    assert received_timestamps == expected_order
    assert alerts[0]["driver_name"] == "Beta Driver"
    assert alerts[1]["driver_name"] == "Alpha Driver"
    assert alerts[2]["driver_name"] == "Gamma Driver"
    assert alerts[3]["driver_name"] == "Beta Driver"
    assert alerts[4]["driver_name"] == "Alpha Driver"


def test_incident_tie_breaking_by_incident_id_desc(multi_driver_incidents_setup):
    """
    When occurrence timestamps are equal, incident_id descending must be the secondary sort key.
    """
    conn = multi_driver_incidents_setup["conn"]
    owner_id = multi_driver_incidents_setup["owner_id"]
    driver_alpha = multi_driver_incidents_setup["driver_alpha"]
    driver_beta = multi_driver_incidents_setup["driver_beta"]

    identical_time = "2026-10-22T12:00:00+00:00"

    # Insert two incidents with identical timestamps
    cursor1 = conn.execute(
        """
        INSERT INTO monitoring_incidents
          (session_id, driver_id, vehicle_id, owner_id, timestamp, event_type, alert_level)
        VALUES (1, ?, 1, ?, ?, 'warning', 2)
        """,
        (driver_alpha, owner_id, identical_time)
    )
    id1 = cursor1.lastrowid

    cursor2 = conn.execute(
        """
        INSERT INTO monitoring_incidents
          (session_id, driver_id, vehicle_id, owner_id, timestamp, event_type, alert_level)
        VALUES (2, ?, 2, ?, ?, 'critical', 3)
        """,
        (driver_beta, owner_id, identical_time)
    )
    id2 = cursor2.lastrowid
    conn.commit()

    assert id2 > id1

    client = multi_driver_incidents_setup["client"]
    response = client.get("/incidents")
    assert response.status_code == 200
    incidents = response.json()

    # The top 2 incidents have the newest identical time
    assert incidents[0]["timestamp"] == identical_time
    assert incidents[1]["timestamp"] == identical_time
    # Secondary sort: higher incident_id must appear first
    assert incidents[0]["incident_id"] == id2
    assert incidents[1]["incident_id"] == id1
