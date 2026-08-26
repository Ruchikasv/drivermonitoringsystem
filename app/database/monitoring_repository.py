import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


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
    status: str  # 'ACTIVE' | 'PAUSED' | 'COMPLETED' | 'INTERRUPTED'
    owner_id: Optional[int] = None
    session_token: Optional[str] = None
    pause_started_at: Optional[str] = None
    total_paused_seconds: float = 0.0


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
    owner_id: Optional[int] = None


@dataclass
class DriverSafetyRating:
    rating_id: Optional[int]
    driver_id: int
    safety_score: Optional[float]
    total_sessions: int
    total_incidents: int
    critical_incidents: int
    last_updated: str
    owner_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class MonitoringRepository:

    def __init__(self, conn: Any):
        self._conn = conn

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def get_active_session_by_driver(self, driver_id: int, owner_id: Optional[int] = None) -> Optional[MonitoringSession]:
        """Return the single ACTIVE running session for a driver, strictly scoped by owner if provided."""
        if owner_id is not None:
            row = self._conn.execute(
                """
                SELECT * FROM monitoring_sessions 
                WHERE driver_id = ? AND status = 'ACTIVE' AND end_time IS NULL 
                  AND owner_id = ?
                ORDER BY session_id DESC LIMIT 1
                """,
                (driver_id, owner_id),
            ).fetchone()
        else:
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

    def get_live_session_by_driver(self, driver_id: int, owner_id: Optional[int] = None) -> Optional[MonitoringSession]:
        """Return any active or paused open session for a driver."""
        if owner_id is not None:
            row = self._conn.execute(
                """
                SELECT * FROM monitoring_sessions 
                WHERE driver_id = ? AND status IN ('ACTIVE', 'PAUSED') AND end_time IS NULL 
                  AND owner_id = ?
                ORDER BY session_id DESC LIMIT 1
                """,
                (driver_id, owner_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT * FROM monitoring_sessions 
                WHERE driver_id = ? AND status IN ('ACTIVE', 'PAUSED') AND end_time IS NULL 
                ORDER BY session_id DESC LIMIT 1
                """,
                (driver_id,),
            ).fetchone()
        if not row:
            return None
        return MonitoringSession(**dict(row))

    def close_active_sessions_for_driver(self, driver_id: int, status: str = "INTERRUPTED") -> int:
        """Explicitly close any existing ACTIVE or PAUSED sessions for a driver."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            UPDATE monitoring_sessions
            SET end_time = ?, status = ?, pause_started_at = NULL
            WHERE driver_id = ? AND status IN ('ACTIVE', 'PAUSED') AND end_time IS NULL
            """,
            (now, status, driver_id),
        )
        self._conn.commit()
        return cursor.rowcount

    def create_session(
        self,
        driver_id: int,
        vehicle_id: Optional[int],
        owner_id: Optional[int] = None,
        session_token: Optional[str] = None,
        close_existing_active: bool = True,
    ) -> int:
        """
        Insert a new ACTIVE monitoring session for a driver with a secure session_token.
        """
        now = datetime.now(timezone.utc).isoformat()
        if close_existing_active:
            self.close_active_sessions_for_driver(driver_id, status="INTERRUPTED")

        if not session_token:
            session_token = secrets.token_urlsafe(32)

        # If owner_id is not provided, inherit from driver if available
        if owner_id is None:
            d_row = self._conn.execute("SELECT owner_id FROM drivers WHERE driver_id = ?", (driver_id,)).fetchone()
            if d_row:
                keys = d_row.keys() if hasattr(d_row, "keys") else []
                if "owner_id" in keys and d_row["owner_id"] is not None:
                    owner_id = d_row["owner_id"]

        cursor = self._conn.execute(
            """
            INSERT INTO monitoring_sessions (driver_id, vehicle_id, owner_id, session_token, start_time, status, total_paused_seconds)
            VALUES (?, ?, ?, ?, ?, 'ACTIVE', 0.0)
            """,
            (driver_id, vehicle_id, owner_id, session_token, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_session(self, session_id: int, owner_id: Optional[int] = None) -> Optional[MonitoringSession]:
        if owner_id is not None:
            row = self._conn.execute(
                """
                SELECT * FROM monitoring_sessions
                WHERE session_id = ? AND owner_id = ?
                """,
                (session_id, owner_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM monitoring_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        return MonitoringSession(**dict(row))

    def get_session_by_token(self, session_id: int, session_token: str) -> Optional[MonitoringSession]:
        """Validate and fetch active/paused session matching session_id and cryptographically secure session_token."""
        if not session_token:
            return None
        row = self._conn.execute(
            """
            SELECT * FROM monitoring_sessions
            WHERE session_id = ? AND session_token = ? AND status IN ('ACTIVE', 'PAUSED') AND end_time IS NULL
            """,
            (session_id, session_token.strip()),
        ).fetchone()
        if not row:
            return None
        return MonitoringSession(**dict(row))

    def get_active_sessions(self, owner_id: Optional[int] = None, include_paused: bool = True) -> list[MonitoringSession]:
        """Return currently active and optionally paused monitoring sessions, strictly scoped by owner if provided."""
        status_clause = "status IN ('ACTIVE', 'PAUSED')" if include_paused else "status = 'ACTIVE'"
        if owner_id is not None:
            rows = self._conn.execute(
                f"""
                SELECT * FROM monitoring_sessions 
                WHERE {status_clause} AND end_time IS NULL 
                  AND owner_id = ?
                ORDER BY start_time DESC
                """,
                (owner_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"""
                SELECT * FROM monitoring_sessions 
                WHERE {status_clause} AND end_time IS NULL 
                ORDER BY start_time DESC
                """
            ).fetchall()
        return [MonitoringSession(**dict(r)) for r in rows]

    def pause_session(self, session_id: int, owner_id: Optional[int] = None) -> bool:
        """
        Transition session from ACTIVE -> PAUSED and record pause start timestamp.
        """
        session = self.get_session(session_id, owner_id=owner_id)
        if not session:
            return False
        if session.status != "ACTIVE" or session.end_time is not None:
            return False

        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            UPDATE monitoring_sessions
            SET status = 'PAUSED', pause_started_at = ?
            WHERE session_id = ? AND status = 'ACTIVE' AND end_time IS NULL
            """,
            (now, session_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def resume_session(self, session_id: int, owner_id: Optional[int] = None) -> bool:
        """
        Transition session from PAUSED -> ACTIVE, accumulate paused duration into total_paused_seconds,
        and clear pause_started_at.
        """
        session = self.get_session(session_id, owner_id=owner_id)
        if not session:
            return False
        if session.status != "PAUSED" or session.end_time is not None:
            return False

        now_dt = datetime.now(timezone.utc)
        additional_paused = 0.0
        if session.pause_started_at:
            try:
                pause_dt = datetime.fromisoformat(session.pause_started_at)
                if pause_dt.tzinfo is None:
                    pause_dt = pause_dt.replace(tzinfo=timezone.utc)
                additional_paused = max(0.0, (now_dt - pause_dt).total_seconds())
            except Exception:
                pass

        total_paused = float(session.total_paused_seconds or 0.0) + additional_paused

        cursor = self._conn.execute(
            """
            UPDATE monitoring_sessions
            SET status = 'ACTIVE', pause_started_at = NULL, total_paused_seconds = ?
            WHERE session_id = ? AND status = 'PAUSED' AND end_time IS NULL
            """,
            (round(total_paused, 2), session_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def end_session(self, session_id: int, status: str = "COMPLETED") -> bool:
        """
        Mark a session completed or interrupted, finalize any active pause duration, and record the end timestamp.
        """
        session = self.get_session(session_id)
        if not session or session.end_time is not None:
            return False

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        total_paused = float(session.total_paused_seconds or 0.0)
        if session.status == "PAUSED" and session.pause_started_at:
            try:
                pause_dt = datetime.fromisoformat(session.pause_started_at)
                if pause_dt.tzinfo is None:
                    pause_dt = pause_dt.replace(tzinfo=timezone.utc)
                total_paused += max(0.0, (now_dt - pause_dt).total_seconds())
            except Exception:
                pass

        cursor = self._conn.execute(
            """
            UPDATE monitoring_sessions
            SET end_time = ?, status = ?, pause_started_at = NULL, total_paused_seconds = ?
            WHERE session_id = ? AND status IN ('ACTIVE', 'PAUSED') AND end_time IS NULL
            """,
            (now_iso, status, round(total_paused, 2), session_id),
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
        owner_id: Optional[int] = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        if owner_id is None:
            s_row = self._conn.execute("SELECT owner_id FROM monitoring_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if s_row:
                keys = s_row.keys() if hasattr(s_row, "keys") else []
                if "owner_id" in keys and s_row["owner_id"] is not None:
                    owner_id = s_row["owner_id"]

        cursor = self._conn.execute(
            """
            INSERT INTO monitoring_incidents
              (session_id, driver_id, vehicle_id, owner_id, timestamp, event_type, alert_level,
               kss_score, ear, mar, perclos, head_pitch_deg, evidence_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, driver_id, vehicle_id, owner_id, now, event_type, alert_level,
             kss_score, ear, mar, perclos, head_pitch_deg, evidence_path),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_incident(self, incident_id: int, owner_id: Optional[int] = None) -> Optional[MonitoringIncident]:
        if owner_id is not None:
            row = self._conn.execute(
                """
                SELECT * FROM monitoring_incidents
                WHERE incident_id = ? AND owner_id = ?
                """,
                (incident_id, owner_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM monitoring_incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        if not row:
            return None
        return MonitoringIncident(**dict(row))

    def get_all_incidents(self, owner_id: Optional[int] = None, limit: int = 200) -> list[MonitoringIncident]:
        if owner_id is not None:
            rows = self._conn.execute(
                """
                SELECT * FROM monitoring_incidents
                WHERE owner_id = ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (owner_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM monitoring_incidents ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [MonitoringIncident(**dict(r)) for r in rows]

    def get_incidents_by_driver(self, driver_id: int, owner_id: Optional[int] = None) -> list[MonitoringIncident]:
        if owner_id is not None:
            rows = self._conn.execute(
                """
                SELECT * FROM monitoring_incidents
                WHERE driver_id = ? AND owner_id = ?
                ORDER BY timestamp DESC
                """,
                (driver_id, owner_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM monitoring_incidents WHERE driver_id = ? ORDER BY timestamp DESC",
                (driver_id,),
            ).fetchall()
        return [MonitoringIncident(**dict(r)) for r in rows]

    def get_incidents_by_session(self, session_id: int, owner_id: Optional[int] = None) -> list[MonitoringIncident]:
        if owner_id is not None:
            rows = self._conn.execute(
                """
                SELECT * FROM monitoring_incidents
                WHERE session_id = ? AND owner_id = ?
                ORDER BY timestamp DESC
                """,
                (session_id, owner_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM monitoring_incidents WHERE session_id = ? ORDER BY timestamp DESC",
                (session_id,),
            ).fetchall()
        return [MonitoringIncident(**dict(r)) for r in rows]

    def delete_incident_evidence(self, incident_id: int, owner_id: Optional[int] = None) -> bool:
        """
        Delete the physical screenshot file and clear the evidence_path
        in the database for this incident, scoped strictly to the authorized owner.
        """
        import os
        from app.config import settings

        incident = self.get_incident(incident_id, owner_id=owner_id)
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

    def get_safety_rating(self, driver_id: int, owner_id: Optional[int] = None) -> Optional[DriverSafetyRating]:
        if owner_id is not None:
            row = self._conn.execute(
                """
                SELECT * FROM driver_safety_ratings
                WHERE driver_id = ? AND owner_id = ?
                """,
                (driver_id, owner_id),
            ).fetchone()
        else:
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
        d_row = self._conn.execute("SELECT owner_id FROM drivers WHERE driver_id = ?", (driver_id,)).fetchone()
        owner_id = None
        if d_row:
            keys = d_row.keys() if hasattr(d_row, "keys") else []
            if "owner_id" in keys:
                owner_id = d_row["owner_id"]

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
              (driver_id, safety_score, total_sessions, total_incidents, critical_incidents, last_updated, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(driver_id) DO UPDATE SET
              safety_score       = excluded.safety_score,
              total_sessions     = excluded.total_sessions,
              total_incidents    = excluded.total_incidents,
              critical_incidents = excluded.critical_incidents,
              last_updated       = excluded.last_updated,
              owner_id           = excluded.owner_id
            """,
            (driver_id, safety_score, total_sessions, total_incidents, critical_incidents, now, owner_id),
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
            owner_id=owner_id,
        )
