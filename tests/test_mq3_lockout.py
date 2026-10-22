"""
Focused tests for MQ-3 alcohol detection state machine and backend trip lockout.

Covers:
- Warm-up and calibration state transitions (ignoring premature detections)
- Threshold persistence requirement before triggering POTENTIAL_ALCOHOL_DETECTED
- Duplicate incident prevention across multiple high readings
- Lockout persistence even when vapor readings drop back to normal
- Backend API blocking for trip creation and trip resumption (HTTP 423)
- Prototype alarm acknowledgement (sets is_acknowledged=True without unlocking)
- Authorization enforcement on lockout resolution (rejects unauthenticated/unauthorized)
- Authorized owner resolution workflow (clears lockout and records reason)
"""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.owner_auth import create_access_token
from app.database.connection import get_connection_context
from app.database.monitoring_repository import MonitoringRepository
from app.hardware.alcohol_sensor import (
    MQ3SerialReader,
    mq3_serial_reader,
    STATE_WARMING_UP,
    STATE_CALIBRATING,
    STATE_NORMAL,
    STATE_POTENTIAL_ALCOHOL,
)


@pytest.fixture(autouse=True)
def clean_lockout_state():
    """Ensure clean isolated state before and after each test."""
    mq3_serial_reader.reset_state_for_testing()
    yield
    mq3_serial_reader.reset_state_for_testing()


def get_test_owner_headers() -> dict:
    headers, _ = get_test_owner_info()
    return headers


def get_test_owner_info() -> tuple[dict, int]:
    """Create a verified owner auth token header and return (headers, owner_id)."""
    with get_connection_context() as conn:
        owner_row = conn.execute("SELECT owner_id, email FROM owners WHERE is_active = 1 LIMIT 1").fetchone()
        if not owner_row:
            cursor = conn.execute(
                "INSERT INTO owners (name, email, password_hash, created_at, is_active) VALUES (?, ?, ?, ?, ?)",
                ("Fleet Manager", "testowner@fleet.com", "hash", "2026-10-21T00:00:00Z", 1),
            )
            conn.commit()
            owner_id = cursor.lastrowid
            email = "testowner@fleet.com"
        else:
            owner_id = owner_row["owner_id"] if hasattr(owner_row, "__getitem__") else owner_row[0]
            email = owner_row["email"] if hasattr(owner_row, "__getitem__") else owner_row[1]

    token = create_access_token(data={"sub": str(owner_id), "email": email})
    return {"Authorization": f"Bearer {token}"}, int(owner_id)


def get_or_create_test_driver() -> int:
    """Ensure a driver exists for foreign key constraints in session tests."""
    with get_connection_context() as conn:
        row = conn.execute("SELECT driver_id FROM drivers LIMIT 1").fetchone()
        if row:
            return row["driver_id"] if hasattr(row, "__getitem__") else row[0]

        cursor = conn.execute(
            "INSERT INTO drivers (name, created_at, is_active) VALUES (?, ?, ?)",
            ("Test Driver", "2026-10-21T00:00:00Z", 1),
        )
        conn.commit()
        return cursor.lastrowid


# ---------------------------------------------------------------------------
# 1. Warm-up and Calibration State Handling
# ---------------------------------------------------------------------------

def test_warmup_and_calibration_state_handling():
    """Verify readings during warm-up and calibration do not trigger alcohol detection."""
    reader = MQ3SerialReader(
        warmup_duration_s=5.0,  # 5s warm-up
        calibration_samples=3,
        threshold=200,
        persistence_count=2,
    )
    # 1. Warm-up phase: high reading of 400 must NOT trigger lockout
    reader.process_reading(analog=400, digital=0)
    status = reader.get_latest_reading()
    assert status["state"] == STATE_WARMING_UP
    assert status["is_locked"] is False

    # Simulate warm-up expiration
    reader._warmup_start_epoch = 1.0  # long ago
    reader.process_reading(analog=68, digital=1)
    status = reader.get_latest_reading()
    assert status["state"] == STATE_CALIBRATING

    # Feed calibration samples
    reader.process_reading(analog=70, digital=1)
    reader.process_reading(analog=72, digital=1)
    status = reader.get_latest_reading()
    assert status["state"] == STATE_NORMAL
    assert status["baseline"] == 70.0


# ---------------------------------------------------------------------------
# 2. Threshold Persistence & Lockout Activation
# ---------------------------------------------------------------------------

def test_threshold_persistence_triggers_lockout():
    """Verify that reading must stay above threshold for persistence_count samples."""
    reader = MQ3SerialReader(
        warmup_duration_s=0.0,  # bypass warm-up for test
        calibration_samples=0,  # bypass calibration
        threshold=200,
        persistence_count=3,
    )
    reader._current_state = STATE_NORMAL

    # Sample 1 above threshold
    reader.process_reading(analog=250, digital=0)
    assert reader.is_locked() is False
    assert reader._current_state == STATE_NORMAL

    # Sample 2 above threshold
    reader.process_reading(analog=260, digital=0)
    assert reader.is_locked() is False

    # Sample 3 reaches persistence count (3)
    reader.process_reading(analog=270, digital=0)
    assert reader.is_locked() is True
    assert reader._current_state == STATE_POTENTIAL_ALCOHOL

    lockout = reader.get_active_lockout()
    assert lockout is not None
    assert lockout["is_locked"] is True
    assert lockout["raw_reading"] == 270


# ---------------------------------------------------------------------------
# 3. Duplicate Prevention
# ---------------------------------------------------------------------------

def test_duplicate_incident_prevention():
    """Ensure only one incident and one active lockout are created per episode."""
    driver_id = get_or_create_test_driver()
    with get_connection_context() as conn:
        m_repo = MonitoringRepository(conn)
        sess_id = m_repo.create_session(driver_id=driver_id, vehicle_id=None)

    mq3_serial_reader.warmup_duration_s = 0.0
    mq3_serial_reader.calibration_sample_target = 0
    mq3_serial_reader.threshold = 200
    mq3_serial_reader.persistence_threshold = 2
    mq3_serial_reader._current_state = STATE_NORMAL

    # Count initial incidents
    with get_connection_context() as conn:
        initial_count = conn.execute(
            "SELECT COUNT(*) FROM monitoring_incidents WHERE event_type = 'alcohol_detected'"
        ).fetchone()[0]

    # Trigger lockout with 2 samples
    mq3_serial_reader.process_reading(analog=300, digital=0)
    mq3_serial_reader.process_reading(analog=310, digital=0)
    assert mq3_serial_reader.is_locked() is True
    event_id = mq3_serial_reader.get_active_lockout()["event_id"]

    # Stream 10 more high readings
    for val in range(320, 330):
        mq3_serial_reader.process_reading(analog=val, digital=0)

    # Event ID and lockout must be unchanged (no duplicates)
    assert mq3_serial_reader.get_active_lockout()["event_id"] == event_id

    # Count alcohol incidents in DB: exactly +1 added
    with get_connection_context() as conn:
        final_count = conn.execute(
            "SELECT COUNT(*) FROM monitoring_incidents WHERE event_type = 'alcohol_detected'"
        ).fetchone()[0]
        assert final_count == initial_count + 1


# ---------------------------------------------------------------------------
# 4. Lockout Persists When Readings Drop & Across Restarts
# ---------------------------------------------------------------------------

def test_lockout_persists_when_readings_drop():
    """Verify vehicle remains locked out even when vapor drops back to clean baseline."""
    mq3_serial_reader.warmup_duration_s = 0.0
    mq3_serial_reader.calibration_sample_target = 0
    mq3_serial_reader.threshold = 200
    mq3_serial_reader.persistence_threshold = 1
    mq3_serial_reader._current_state = STATE_NORMAL

    # Trigger lockout
    mq3_serial_reader.process_reading(analog=350, digital=0)
    assert mq3_serial_reader.is_locked() is True

    # Vapor drops back to normal clean-air baseline (68)
    for _ in range(5):
        mq3_serial_reader.process_reading(analog=68, digital=1)

    # State returns to NORMAL but lockout MUST remain True
    reading_info = mq3_serial_reader.get_latest_reading()
    assert reading_info["analog"] == 68
    assert reading_info["state"] == STATE_NORMAL
    assert mq3_serial_reader.is_locked() is True
    assert reading_info["is_locked"] is True

    # Test DB persistence across simulated server reboot
    new_reader_instance = MQ3SerialReader()
    assert new_reader_instance.is_locked() is True
    assert new_reader_instance.get_active_lockout()["is_locked"] is True


# ---------------------------------------------------------------------------
# 5. Backend Trip Blocking (HTTP 423)
# ---------------------------------------------------------------------------

def test_trip_blocking_when_locked():
    """Ensure starting or resuming a trip returns HTTP 423 when lockout is active."""
    driver_id = get_or_create_test_driver()

    # Force active lockout
    mq3_serial_reader.warmup_duration_s = 0.0
    mq3_serial_reader.calibration_sample_target = 0
    mq3_serial_reader.threshold = 200
    mq3_serial_reader.persistence_threshold = 1
    mq3_serial_reader._current_state = STATE_NORMAL
    mq3_serial_reader.process_reading(analog=300, digital=0)
    assert mq3_serial_reader.is_locked() is True

    client = TestClient(app)

    # Attempt to start trip
    create_resp = client.post("/sessions/", json={"driver_id": driver_id, "vehicle_id": None})
    assert create_resp.status_code == 423
    assert "VEHICLE OPERATION LOCKED OUT" in create_resp.json()["detail"]

    # Attempt to resume trip
    resume_resp = client.post("/sessions/999/resume")
    assert resume_resp.status_code == 423
    assert "VEHICLE OPERATION LOCKED OUT" in resume_resp.json()["detail"]


# ---------------------------------------------------------------------------
# 6. Separate Alarm Acknowledgement (Does NOT Unlock Trip)
# ---------------------------------------------------------------------------

def test_alarm_acknowledgement_does_not_unlock():
    """Driver acknowledgement silences alarm but vehicle remains locked out."""
    mq3_serial_reader.warmup_duration_s = 0.0
    mq3_serial_reader.calibration_sample_target = 0
    mq3_serial_reader.threshold = 200
    mq3_serial_reader.persistence_threshold = 1
    mq3_serial_reader._current_state = STATE_NORMAL
    mq3_serial_reader.process_reading(analog=300, digital=0)

    client = TestClient(app)
    resp = client.post("/api/alcohol/acknowledge")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_acknowledged"] is True
    assert data["is_locked"] is True

    # Lockout must still be active
    assert mq3_serial_reader.is_locked() is True


# ---------------------------------------------------------------------------
# 7. Authorization Enforcement on Resolution
# ---------------------------------------------------------------------------

def test_unauthorized_resolution_blocked():
    """Unauthenticated calls or missing owner credentials must be rejected with 401."""
    mq3_serial_reader.warmup_duration_s = 0.0
    mq3_serial_reader.calibration_sample_target = 0
    mq3_serial_reader.threshold = 200
    mq3_serial_reader.persistence_threshold = 1
    mq3_serial_reader._current_state = STATE_NORMAL
    mq3_serial_reader.process_reading(analog=300, digital=0)

    client = TestClient(app)

    # 1. No auth headers
    resp = client.post("/api/alcohol/resolve", json={"reason": "Driver was tested and cleared"})
    assert resp.status_code == 401

    # 2. Invalid auth header
    bad_resp = client.post(
        "/api/alcohol/resolve",
        json={"reason": "Driver was tested and cleared"},
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert bad_resp.status_code == 401


# ---------------------------------------------------------------------------
# 8. Authorized Owner Resolution Workflow
# ---------------------------------------------------------------------------

def test_authorized_owner_resolution_clears_lockout():
    """Authorized owner provides a reason to clear lockout and allow trips."""
    driver_id = get_or_create_test_driver()

    mq3_serial_reader.warmup_duration_s = 0.0
    mq3_serial_reader.calibration_sample_target = 0
    mq3_serial_reader.threshold = 200
    mq3_serial_reader.persistence_threshold = 1
    mq3_serial_reader._current_state = STATE_NORMAL
    mq3_serial_reader.process_reading(analog=300, digital=0)
    assert mq3_serial_reader.is_locked() is True

    client = TestClient(app)
    headers = get_test_owner_headers()

    # Owner resolves with audit reason
    resolve_resp = client.post(
        "/api/alcohol/resolve",
        json={"reason": "Secondary certified breathalyzer confirmed 0.00% BAC. False vapor alarm."},
        headers=headers,
    )
    assert resolve_resp.status_code == 200
    result = resolve_resp.json()
    assert result["success"] is True
    assert result["resolved_event"]["is_resolved"] is True
    assert "Secondary certified breathalyzer" in result["resolved_event"]["resolution_reason"]

    # Lockout is now cleared!
    assert mq3_serial_reader.is_locked() is False

    # Trip start is now allowed
    start_resp = client.post("/sessions/", json={"driver_id": driver_id, "vehicle_id": None}, headers=headers)
    assert start_resp.status_code in (201, 200)


# ---------------------------------------------------------------------------
# 9. Regression Tests: Active Lockout with Below-Threshold Reading (e.g. 167 < 200)
# ---------------------------------------------------------------------------

def test_active_lockout_with_below_threshold_reading_enforces_restricted_session():
    """
    Regression test for observed Live Surveillance issue:
    - Lockout triggered previously (e.g. 250 >= 200).
    - Current sensor reading drops to 167 (below threshold 200).
    - Lockout MUST remain active (is_locked=True).
    - Active sessions MUST report status="PAUSED", is_paused=True, is_locked=True.
    - Live metrics cache MUST report risk_level="RESTRICTED" and kss_label="Operation Restricted".
    - Resumes and new starts must continue to be blocked with HTTP 423.
    """
    driver_id = get_or_create_test_driver()
    client = TestClient(app)
    headers, owner_id = get_test_owner_info()

    # 1. Start a trip normally before any lockout using owner auth
    create_init = client.post("/sessions/", json={"driver_id": driver_id, "vehicle_id": None}, headers=headers)
    assert create_init.status_code in (200, 201)
    sess_id = create_init.json()["session_id"]

    # Populate live metrics cache simulating active streaming
    from app.api.monitoring_ws import LIVE_SESSION_METRICS
    LIVE_SESSION_METRICS[sess_id] = {
        "session_id": sess_id,
        "status": "ACTIVE",
        "is_paused": False,
        "is_locked": False,
        "critical_active": False,
        "driver_id": driver_id,
        "driver_name": "Test Driver",
        "vehicle_registration": "MH-01-AB-1234",
        "owner_id": owner_id,
        "metrics": {"risk_level": "LOW", "ear": 0.32, "mar": 0.22, "perclos": 0.02},
        "fusion": {"kss_now": 2.0, "kss_label": "Attentive"},
        "latest_alert": None,
    }

    # 2. Trigger alcohol lockout
    mq3_serial_reader.warmup_duration_s = 0.0
    mq3_serial_reader.calibration_sample_target = 0
    mq3_serial_reader.threshold = 200
    mq3_serial_reader.persistence_threshold = 1
    mq3_serial_reader._current_state = STATE_NORMAL
    mq3_serial_reader.process_reading(analog=250, digital=0)
    assert mq3_serial_reader.is_locked() is True

    # Check that active session was automatically paused in DB
    with get_connection_context() as conn:
        repo = MonitoringRepository(conn)
        s = repo.get_session(sess_id)
        assert s.status == "PAUSED"
        assert s.pause_started_at is not None

    # 3. Reading falls to 167 (well below threshold 200)
    mq3_serial_reader.process_reading(analog=167, digital=1)

    # Lockout MUST NOT clear from a lower reading alone!
    assert mq3_serial_reader.is_locked() is True
    status_resp = client.get("/api/alcohol/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["is_locked"] is True
    assert status_data["analog"] == 167
    assert status_data["threshold"] == 200

    # 4. Check active sessions API endpoint
    active_resp = client.get("/sessions/active", headers=headers)
    assert active_resp.status_code == 200
    active_sessions = active_resp.json()
    matching = [s for s in active_sessions if s["session_id"] == sess_id]
    assert len(matching) == 1
    assert matching[0]["is_locked"] is True
    assert matching[0]["status"] == "PAUSED"
    assert matching[0]["is_paused"] is True

    # 5. Check live metrics API endpoint
    live_resp = client.get("/sessions/live/all", headers=headers)
    assert live_resp.status_code == 200
    live_all = live_resp.json()
    assert str(sess_id) in live_all or sess_id in live_all
    sess_metrics = live_all.get(str(sess_id)) or live_all.get(sess_id)
    assert sess_metrics["is_locked"] is True
    assert sess_metrics["status"] == "PAUSED"
    assert sess_metrics["is_paused"] is True
    assert sess_metrics["metrics"]["risk_level"] == "RESTRICTED"
    assert sess_metrics["fusion"]["kss_label"] == "Operation Restricted"

    # 6. Attempting to resume returns HTTP 423
    resume_resp = client.post(f"/sessions/{sess_id}/resume", headers=headers)
    assert resume_resp.status_code == 423
    assert "VEHICLE OPERATION LOCKED OUT" in resume_resp.json()["detail"]

    # 7. Authorized owner clears lockout
    resolve_resp = client.post(
        "/api/alcohol/resolve",
        json={"reason": "Secondary fuel-cell breathalyzer verified 0.00% BAC. Owner authorized clearance."},
        headers=headers,
    )
    assert resolve_resp.status_code == 200
    assert mq3_serial_reader.is_locked() is False

    # 8. After resolution, session can be resumed successfully
    resume_ok = client.post(f"/sessions/{sess_id}/resume", headers=headers)
    assert resume_ok.status_code == 200
    assert resume_ok.json()["status"] == "ACTIVE"
    assert resume_ok.json()["is_locked"] is False
    assert resume_ok.json()["is_paused"] is False
