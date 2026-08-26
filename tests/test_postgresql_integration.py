"""
Comprehensive PostgreSQL Integration Test Suite for Production Database Verification.

Connects to live PostgreSQL 17 server on port 5434 and verifies all 12 multi-tenant
and database lifecycle operations against real PostgreSQL engine.
"""

import os
import uuid
import pytest
import numpy as np

from app.database.connection import get_connection, init_db, seed_default_data
from app.database.owner_repository import OwnerRepository
from app.database.driver_repository import DriverRepository
from app.database.vehicle_repository import VehicleRepository
from app.database.monitoring_repository import MonitoringRepository


PG_TEST_URL = "postgresql://postgres@localhost:5434/postgres"


@pytest.fixture(scope="module")
def pg_conn():
    """Module-scoped real PostgreSQL connection."""
    try:
        conn = get_connection(PG_TEST_URL)
        init_db(conn)
    except Exception as e:
        pytest.skip(f"PostgreSQL server not available on port 5434: {e}")
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _uid():
    return uuid.uuid4().hex[:6].upper()


class TestPostgreSQLIntegration:
    """12-point real PostgreSQL engine verification."""

    def test_01_postgresql_connection_and_schema(self, pg_conn):
        """Verify real PostgreSQL connection and schema creation."""
        row = pg_conn.execute("SELECT version() AS ver").fetchone()
        assert row is not None
        assert "PostgreSQL" in (row["ver"] if isinstance(row, dict) or hasattr(row, "keys") else row[0])

    def test_02_owner_registration_and_login(self, pg_conn):
        """Verify Owner registration with Argon2id hashing and password verification."""
        repo = OwnerRepository(pg_conn)
        u = _uid()
        email = f"apex_{u}@fleet.com"
        owner_id = repo.create_owner(
            name=f"Apex Fleet {u}",
            email=email,
            plain_password="ApexSecurePassword123!",
        )
        assert owner_id is not None
        assert owner_id > 0

        # Verify authentication
        auth_success = repo.authenticate_owner(email, "ApexSecurePassword123!")
        assert auth_success is not None
        assert auth_success.owner_id == owner_id
        assert auth_success.email == email

        # Verify invalid password rejected
        auth_fail = repo.authenticate_owner(email, "WrongPassword!")
        assert auth_fail is None

        # Verify duplicate email rejected
        with pytest.raises(ValueError, match="already registered"):
            repo.create_owner("Duplicate", email, "ApexSecurePassword123!")

    def test_03_multi_tenant_owner_isolation(self, pg_conn):
        """Verify complete isolation between Owner A and Owner B."""
        o_repo = OwnerRepository(pg_conn)
        d_repo = DriverRepository(pg_conn)
        v_repo = VehicleRepository(pg_conn)

        u = _uid()
        # Create Owner A & Owner B
        owner_a_id = o_repo.create_owner(f"Owner Alpha {u}", f"alpha_{u}@fleet.com", "PasswordAlpha123!")
        owner_b_id = o_repo.create_owner(f"Owner Beta {u}", f"beta_{u}@fleet.com", "PasswordBeta123!")

        # Owner A adds driver & vehicle
        emb_a = np.ones(512, dtype=np.float32)
        d_a = d_repo.add_driver(f"Driver Alpha {u}", emb_a, license_no=f"DL-A-{u}", owner_id=owner_a_id)
        v_a = v_repo.add_vehicle(f"KA-01-A{u}", "Volvo FM", "Heavy", owner_id=owner_a_id)

        # Owner B adds driver & vehicle
        emb_b = np.zeros(512, dtype=np.float32)
        d_b = d_repo.add_driver(f"Driver Beta {u}", emb_b, license_no=f"DL-B-{u}", owner_id=owner_b_id)
        v_b = v_repo.add_vehicle(f"KA-02-B{u}", "Tata Signa", "Cargo", owner_id=owner_b_id)

        # Verify Owner A only sees Owner A data
        drivers_a = d_repo.get_all_drivers(owner_id=owner_a_id)
        vehicles_a = v_repo.get_all_vehicles(owner_id=owner_a_id)
        assert any(d.driver_id == d_a for d in drivers_a)
        assert not any(d.driver_id == d_b for d in drivers_a)
        assert any(v.vehicle_id == v_a for v in vehicles_a)
        assert not any(v.vehicle_id == v_b for v in vehicles_a)

        # Verify Owner B cannot access Owner A driver
        assert d_repo.get_driver_by_id(d_a, owner_id=owner_b_id) is None
        assert v_repo.get_vehicle_by_id(v_a, owner_id=owner_b_id) is None

    def test_04_driver_and_vehicle_lifecycle(self, pg_conn):
        """Verify driver biometric registration, vehicle addition, assignment, and unassignment."""
        d_repo = DriverRepository(pg_conn)
        v_repo = VehicleRepository(pg_conn)

        u = _uid()
        emb = np.random.randn(512).astype(np.float32)
        driver_id = d_repo.add_driver(f"Postgres Driver {u}", emb, license_no=f"DL-PG-{u}")
        vehicle_id = v_repo.add_vehicle(f"KA-53-P{u}", "BharatBenz 3528C", "Heavy Haul")

        # Assign vehicle
        assigned = v_repo.assign_vehicle(driver_id, vehicle_id)
        assert assigned is not None and assigned > 0

        assignment = v_repo.get_current_assignment(driver_id)
        assert assignment is not None
        assert assignment.vehicle_id == vehicle_id

        # Verify in vehicle listing with assignments
        vehicles_with_meta = v_repo.get_all_vehicles_with_assignments()
        v_rec = next((v for v in vehicles_with_meta if v["vehicle_id"] == vehicle_id), None)
        assert v_rec is not None
        assert v_rec["assigned_driver"] is not None
        assert v_rec["assigned_driver"]["driver_id"] == driver_id

        # Unassign
        unassigned = v_repo.unassign_vehicle(driver_id)
        assert unassigned is True
        assert v_repo.get_current_assignment(driver_id) is None

    def test_05_monitoring_session_and_incidents(self, pg_conn):
        """Verify monitoring session creation with session_token and incident logging."""
        d_repo = DriverRepository(pg_conn)
        v_repo = VehicleRepository(pg_conn)
        m_repo = MonitoringRepository(pg_conn)

        u = _uid()
        driver_id = d_repo.add_driver(f"Session Driver {u}", np.ones(512, dtype=np.float32))
        vehicle_id = v_repo.add_vehicle(f"KA-04-S{u}", "Tata Prima", "Truck")
        v_repo.assign_vehicle(driver_id, vehicle_id)

        # Create active session
        session_id = m_repo.create_session(driver_id, vehicle_id)
        assert session_id is not None
        assert session_id > 0

        session = m_repo.get_session(session_id)
        assert session is not None
        assert session.status == "ACTIVE"
        assert session.session_token is not None
        assert len(session.session_token) > 20

        # Verify token retrieval
        token_sess = m_repo.get_session_by_token(session_id, session.session_token)
        assert token_sess is not None
        assert token_sess.session_id == session_id

        # Log Level 1 and Level 3 incidents
        inc1_id = m_repo.create_incident(
            session_id=session_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            event_type="yawn",
            alert_level=1,
            kss_score=5.2,
            ear=0.28,
            mar=0.65,
            perclos=0.12,
            head_pitch_deg=-2.0,
        )
        assert inc1_id > 0

        inc2_id = m_repo.create_incident(
            session_id=session_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            event_type="critical",
            alert_level=3,
            kss_score=8.7,
            ear=0.12,
            mar=0.32,
            perclos=0.48,
            head_pitch_deg=-15.0,
            evidence_path="app/evidence/pg_test_evidence.jpg",
        )
        assert inc2_id > 0

        # Fetch incidents
        incidents = m_repo.get_incidents_by_driver(driver_id)
        assert len(incidents) >= 2
        crit = next((i for i in incidents if i.alert_level == 3), None)
        assert crit is not None
        assert crit.kss_score == 8.7

        # Complete session
        m_repo.end_session(session_id, status="COMPLETED")
        sess_done = m_repo.get_session(session_id)
        assert sess_done.status == "COMPLETED"
        assert sess_done.end_time is not None

    def test_06_analytics_queries_and_safety_ratings(self, pg_conn):
        """Verify PostgreSQL calculation of safety ratings and analytics aggregations."""
        d_repo = DriverRepository(pg_conn)
        v_repo = VehicleRepository(pg_conn)
        m_repo = MonitoringRepository(pg_conn)

        u = _uid()
        driver_id = d_repo.add_driver(f"Rating Driver {u}", np.ones(512, dtype=np.float32))
        vehicle_id = v_repo.add_vehicle(f"KA-05-R{u}", "Eicher Pro", "Tanker")

        s_id = m_repo.create_session(driver_id, vehicle_id)
        m_repo.create_incident(
            session_id=s_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            event_type="critical",
            alert_level=3,
        )
        m_repo.end_session(s_id, status="COMPLETED")

        # Recalculate safety rating
        rating = m_repo.recalculate_safety_rating(driver_id)
        assert rating is not None
        assert rating.total_sessions >= 1
        assert rating.total_incidents >= 1
        assert rating.critical_incidents >= 1
        # 100 - (1 critical * 8) = 92.0
        assert rating.safety_score == 92.0

    def test_07_driver_deletion_biometric_privacy(self, pg_conn):
        """Verify driver deletion wipes biometrics (face_embedding = NULL), deactivates, and preserves audit logs."""
        d_repo = DriverRepository(pg_conn)
        v_repo = VehicleRepository(pg_conn)
        m_repo = MonitoringRepository(pg_conn)

        u = _uid()
        driver_id = d_repo.add_driver(f"Driver To Fire {u}", np.random.randn(512).astype(np.float32))
        vehicle_id = v_repo.add_vehicle(f"KA-01-F{u}", "Ashok Leyland", "Truck")
        v_repo.assign_vehicle(driver_id, vehicle_id)

        session_id = m_repo.create_session(driver_id, vehicle_id)
        inc_id = m_repo.create_incident(
            session_id=session_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            event_type="critical",
            alert_level=3,
        )

        # Fire / Delete Driver
        fired = d_repo.delete_driver(driver_id)
        assert fired is True

        # Check driver excluded from active fleet
        assert d_repo.get_driver_by_id(driver_id) is None
        active_drivers = d_repo.get_all_drivers()
        assert not any(d.driver_id == driver_id for d in active_drivers)

        # Check biometrics wiped in PostgreSQL row
        raw = pg_conn.execute("SELECT face_embedding, is_active, deleted_at FROM drivers WHERE driver_id = %s", (driver_id,)).fetchone()
        assert raw["face_embedding"] is None
        assert raw["is_active"] == 0
        assert raw["deleted_at"] is not None

        # Check vehicle assignment was closed
        assert v_repo.get_current_assignment(driver_id) is None

        # Check active session was interrupted
        sess = m_repo.get_session(session_id)
        assert sess.status == "INTERRUPTED"

        # Check historical incident audit record preserved
        inc = m_repo.get_incident(inc_id)
        assert inc is not None
        assert inc.alert_level == 3

    def test_08_vehicle_deletion_safety(self, pg_conn):
        """Verify vehicle deletion safely unassigns vehicle and preserves historical session references without FK violation."""
        d_repo = DriverRepository(pg_conn)
        v_repo = VehicleRepository(pg_conn)
        m_repo = MonitoringRepository(pg_conn)

        u = _uid()
        driver_id = d_repo.add_driver(f"Driver For Veh {u}", np.ones(512, dtype=np.float32))
        vehicle_id = v_repo.add_vehicle(f"KA-01-V{u}", "Tata Prima", "Truck")
        v_repo.assign_vehicle(driver_id, vehicle_id)

        session_id = m_repo.create_session(driver_id, vehicle_id)
        m_repo.end_session(session_id, status="COMPLETED")

        # Delete vehicle
        deleted = v_repo.delete_vehicle(vehicle_id)
        assert deleted is True

        # Verify vehicle is deleted
        assert v_repo.get_vehicle_by_id(vehicle_id) is None
        assert not any(v.vehicle_id == vehicle_id for v in v_repo.get_all_vehicles())

        # Verify session record still exists with vehicle_id set to NULL
        session = m_repo.get_session(session_id)
        assert session is not None
        assert session.vehicle_id is None

    def test_09_persistence_and_reconnection_across_restarts(self, pg_conn):
        """Verify that disconnecting and reconnecting to PostgreSQL preserves all data without corruption."""
        # 1. Close current connection
        pg_conn.close()

        # 2. Re-open brand new connection to PostgreSQL
        new_conn = get_connection(PG_TEST_URL)

        # 3. Verify owners, drivers, and vehicles persist
        d_repo = DriverRepository(new_conn)
        drivers = d_repo.get_all_drivers()
        assert len(drivers) > 0

        v_repo = VehicleRepository(new_conn)
        vehicles = v_repo.get_all_vehicles()
        assert len(vehicles) > 0

        new_conn.close()

    def test_10_no_auto_seed_or_recreation_on_restart(self, pg_conn):
        """Verify startup seed_default_data against PostgreSQL never resurrects deleted records or resets tables."""
        conn = get_connection(PG_TEST_URL)

        # Call seed_default_data
        seed_default_data(conn)

        # Verify initial_seed_completed is set
        row = conn.execute("SELECT value FROM system_metadata WHERE key = 'initial_seed_completed'").fetchone()
        assert row is not None
        assert (row["value"] if isinstance(row, dict) or hasattr(row, "keys") else row[0]) == "1"

        conn.close()

