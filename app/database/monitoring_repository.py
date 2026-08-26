"""
Repository for monitoring sessions, drowsiness incidents, and driver safety ratings.

All operations go through the same SQLite connection as the existing
DriverRepository and VehicleRepository.  No ORM — raw SQL with named
parameters to stay consistent with the existing codebase style.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MonitoringSession:
    session_id: Optional[int]
    driver_id: int
    vehicle_id: Optional[int]
    start_time: str
    end_time: Optional[str]
    status: str  # 'ACTIVE' | 'COMPLETED' | 'INTERRUPTED'


@dataclass
class MonitoringIncident:
    incident_id: Optional[int]
    session_id: int
    driver_id: int
    vehicle_id: Optional[int]
    timestamp: str
    event_type: str          # 'nudge' | 'warning' | 'critical'
    alert_level: int         # 1 | 2 | 3
    kss_score: Optional[float]
    ear: Optional[float]
    mar: Optional[float]
    perclos: Optional[float]
    head_pitch_deg: Optional[float]
    evidence_path: Optional[str]


@dataclass
class DriverSafetyRating:
    rating_id: Optional[int]
    driver_id: int
    safety_score: Optional[float]
    total_sessions: int
    total_incidents: int
    critical_incidents: int
    last_updated: str


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class MonitoringRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def get_active_session_by_driver(self, driver_id: int) -> Optional[MonitoringSession]:
        """Return the single ACTIVE session for a driver, or None if off-duty."""
        row = self._conn.execute(
            """
            SELECT * FROM monitoring_sessions 
            WHERE driver_id = ? AND status = 'ACTIVE' AND end_time IS NULL 
            ORDER BY session_id DESC LIMIT 1
            """,
            (driver_id,),
        ).fetchone()
        if not row:
            return None
        return MonitoringSession(**dict(row))

    def close_active_sessions_for_driver(self, driver_id: int, status: str = "INTERRUPTED") -> int:
        """Explicitly close any existing ACTIVE sessions for a driver."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            UPDATE monitoring_sessions
            SET end_time = ?, status = ?
            WHERE driver_id = ? AND status = 'ACTIVE'
            """,
            (now, status, driver_id),
        )
        self._conn.commit()
        return cursor.rowcount

    def create_session(self, driver_id: int, vehicle_id: Optional[int], close_existing_active: bool = True) -> int:
        """
        Insert a new ACTIVE monitoring session for a driver.
        Guarantees at most one ACTIVE session per driver by explicitly closing
        any stale active sessions before creating the new one.
        """
        now = datetime.now(timezone.utc).isoformat()
        if close_existing_active:
            self.close_active_sessions_for_driver(driver_id, status="INTERRUPTED")

        cursor = self._conn.execute(
            """
            INSERT INTO monitoring_sessions (driver_id, vehicle_id, start_time, status)
            VALUES (?, ?, ?, 'ACTIVE')
            """,
            (driver_id, vehicle_id, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_session(self, session_id: int) -> Optional[MonitoringSession]:
        row = self._conn.execute(
            "SELECT * FROM monitoring_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        return MonitoringSession(**dict(row))

    def get_active_sessions(self) -> list[MonitoringSession]:
        """Return all currently genuine ACTIVE monitoring sessions (with end_time IS NULL)."""
        rows = self._conn.execute(
            """
            SELECT * FROM monitoring_sessions 
            WHERE status = 'ACTIVE' AND end_time IS NULL 
            ORDER BY start_time DESC
            """
        ).fetchall()
        return [MonitoringSession(**dict(r)) for r in rows]

    def end_session(self, session_id: int, status: str = "COMPLETED") -> bool:
        """Mark a session completed or interrupted and record the end timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            UPDATE monitoring_sessions
            SET end_time = ?, status = ?
            WHERE session_id = ? AND status = 'ACTIVE'
            """,
            (now, status, session_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def interrupt_session(self, session_id: int) -> bool:
        return self.end_session(session_id, status="INTERRUPTED")

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------

    def create_incident(
        self,
        session_id: int,
        driver_id: int,
        vehicle_id: Optional[int],
        event_type: str,
        alert_level: int,
        kss_score: Optional[float] = None,
        ear: Optional[float] = None,
        mar: Optional[float] = None,
        perclos: Optional[float] = None,
        head_pitch_deg: Optional[float] = None,
        evidence_path: Optional[str] = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            INSERT INTO monitoring_incidents
              (session_id, driver_id, vehicle_id, timestamp, event_type, alert_level,
               kss_score, ear, mar, perclos, head_pitch_deg, evidence_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, driver_id, vehicle_id, now, event_type, alert_level,
             kss_score, ear, mar, perclos, head_pitch_deg, evidence_path),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_incident(self, incident_id: int) -> Optional[MonitoringIncident]:
        row = self._conn.execute(
            "SELECT * FROM monitoring_incidents WHERE incident_id = ?", (incident_id,)
        ).fetchone()
        if not row:
            return None
        return MonitoringIncident(**dict(row))

    def get_all_incidents(self, limit: int = 200) -> list[MonitoringIncident]:
        rows = self._conn.execute(
            "SELECT * FROM monitoring_incidents ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [MonitoringIncident(**dict(r)) for r in rows]

    def get_incidents_by_driver(self, driver_id: int) -> list[MonitoringIncident]:
        rows = self._conn.execute(
            "SELECT * FROM monitoring_incidents WHERE driver_id = ? ORDER BY timestamp DESC",
            (driver_id,),
        ).fetchall()
        return [MonitoringIncident(**dict(r)) for r in rows]

    def get_incidents_by_session(self, session_id: int) -> list[MonitoringIncident]:
        rows = self._conn.execute(
            "SELECT * FROM monitoring_incidents WHERE session_id = ? ORDER BY timestamp DESC",
            (session_id,),
        ).fetchall()
        return [MonitoringIncident(**dict(r)) for r in rows]

    def delete_incident_evidence(self, incident_id: int) -> bool:
        """
        Delete the physical screenshot file and clear the evidence_path
        in SQLite for this incident.
        """
        import os
        from app.config import settings

        incident = self.get_incident(incident_id)
        if not incident or not incident.evidence_path:
            return False

        full_path = os.path.join(str(settings.PROJECT_ROOT), incident.evidence_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception:
                pass

        cursor = self._conn.execute(
            "UPDATE monitoring_incidents SET evidence_path = NULL WHERE incident_id = ?",
            (incident_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Safety Ratings
    # ------------------------------------------------------------------

    def get_safety_rating(self, driver_id: int) -> Optional[DriverSafetyRating]:
        row = self._conn.execute(
            "SELECT * FROM driver_safety_ratings WHERE driver_id = ?", (driver_id,)
        ).fetchone()
        if not row:
            return None
        return DriverSafetyRating(**dict(row))

    def recalculate_safety_rating(self, driver_id: int) -> DriverSafetyRating:
        """
        Recalculate a driver's safety rating from their incident history.
        Safety score: 100 minus weighted incident penalty.
            - nudge:    -1 point
            - warning:  -3 points
            - critical: -8 points
        Clamped to [0, 100].  NULL until the driver has at least one session.
        """
        total_sessions = self._conn.execute(
            "SELECT COUNT(*) FROM monitoring_sessions WHERE driver_id = ?", (driver_id,)
        ).fetchone()[0]

        rows = self._conn.execute(
            "SELECT event_type FROM monitoring_incidents WHERE driver_id = ?", (driver_id,)
        ).fetchall()

        total_incidents = len(rows)
        critical_incidents = sum(1 for r in rows if r["event_type"] == "critical")
        warning_incidents = sum(1 for r in rows if r["event_type"] == "warning")
        nudge_incidents = sum(1 for r in rows if r["event_type"] == "nudge")

        if total_sessions == 0:
            safety_score = None
        else:
            penalty = (critical_incidents * 8) + (warning_incidents * 3) + (nudge_incidents * 1)
            safety_score = round(max(0.0, min(100.0, 100.0 - penalty)), 1)

        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """
            INSERT INTO driver_safety_ratings
              (driver_id, safety_score, total_sessions, total_incidents, critical_incidents, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(driver_id) DO UPDATE SET
              safety_score       = excluded.safety_score,
              total_sessions     = excluded.total_sessions,
              total_incidents    = excluded.total_incidents,
              critical_incidents = excluded.critical_incidents,
              last_updated       = excluded.last_updated
            """,
            (driver_id, safety_score, total_sessions, total_incidents, critical_incidents, now),
        )
        self._conn.commit()

        return DriverSafetyRating(
            rating_id=None,
            driver_id=driver_id,
            safety_score=safety_score,
            total_sessions=total_sessions,
            total_incidents=total_incidents,
            critical_incidents=critical_incidents,
            last_updated=now,
        )
