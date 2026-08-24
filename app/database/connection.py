"""
SQLite database connection and schema management.

Provides a factory function for database connections and handles
one-time schema creation (table initialisation).
"""

import sqlite3
from pathlib import Path

from app.config import settings


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Create and return a new SQLite connection.

    Parameters
    ----------
    db_path : Path, optional
        Override the default database path (useful for tests with `:memory:`).

    Returns
    -------
    sqlite3.Connection
        A connection with Row factory enabled for dict-like access.
    """
    if db_path is None:
        db_path = settings.DATABASE_PATH

    # Ensure the parent directory exists.
    if str(db_path) != ":memory:":
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Access columns by name.
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent-read perf.
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """
    Create database tables if they do not already exist, and safely
    migrate columns if extending an existing database.

    This is idempotent — safe to call on every application startup.

    Parameters
    ----------
    conn : sqlite3.Connection
        An open database connection.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drivers (
            driver_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            face_embedding  BLOB   NOT NULL,
            created_at      TEXT    NOT NULL,
            phone           TEXT,
            email           TEXT,
            license_no      TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicles (
            vehicle_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            registration_number  TEXT    NOT NULL UNIQUE,
            model                TEXT    NOT NULL,
            vehicle_type         TEXT    NOT NULL,
            created_at           TEXT    NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS driver_vehicle_assignments (
            assignment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id       INTEGER NOT NULL,
            vehicle_id      INTEGER NOT NULL,
            assigned_at     TEXT    NOT NULL,
            unassigned_at   TEXT,
            FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
        )
        """
    )

    # Idempotent migration for existing database instances:
    # Ensure nullable profile fields exist without altering existing embeddings.
    cursor = conn.execute("PRAGMA table_info(drivers)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    for col in ["phone", "email", "license_no"]:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE drivers ADD COLUMN {col} TEXT")

    # -----------------------------------------------------------------------
    # Phase 2+ — Drowsiness Monitoring Tables
    # All use CREATE TABLE IF NOT EXISTS so they are safe to call on existing
    # databases and do not affect the 42 existing tests (which use :memory:).
    # -----------------------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoring_sessions (
            session_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id    INTEGER NOT NULL,
            vehicle_id   INTEGER,
            start_time   TEXT    NOT NULL,
            end_time     TEXT,
            status       TEXT    NOT NULL DEFAULT 'ACTIVE',
            FOREIGN KEY (driver_id)  REFERENCES drivers(driver_id),
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoring_incidents (
            incident_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id     INTEGER NOT NULL,
            driver_id      INTEGER NOT NULL,
            vehicle_id     INTEGER,
            timestamp      TEXT    NOT NULL,
            event_type     TEXT    NOT NULL,
            alert_level    INTEGER NOT NULL,
            kss_score      REAL,
            ear            REAL,
            mar            REAL,
            perclos        REAL,
            head_pitch_deg REAL,
            evidence_path  TEXT,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS driver_safety_ratings (
            rating_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id          INTEGER NOT NULL UNIQUE,
            safety_score       REAL,
            total_sessions     INTEGER DEFAULT 0,
            total_incidents    INTEGER DEFAULT 0,
            critical_incidents INTEGER DEFAULT 0,
            last_updated       TEXT    NOT NULL,
            FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
        )
        """
    )

    conn.commit()



def seed_default_data(conn: sqlite3.Connection) -> None:
    """Seed initial commercial fleet drivers and vehicles if missing."""
    from datetime import datetime, timezone
    import numpy as np

    now = datetime.now(timezone.utc).isoformat()
    dummy_emb = np.zeros(512, dtype=np.float32).tobytes()

    default_drivers = [
        ("Lakshmi", "+91 98210 99412", "lakshmi@fleetsafety.internal", "DL-KA042021009182"),
        ("Avva", "+91 97401 55219", "avva@fleetsafety.internal", "DL-KA512022003891"),
        ("Vikram Singh", "+91 98210 99412", "vikram.s@fleetsafety.internal", "DL-KA042021009182"),
        ("Anand Kumar", "+91 97401 55219", "anand.k@fleetsafety.internal", "DL-KA512022003891"),
        ("Rajesh Nair", "+91 96112 40012", "rajesh.n@fleetsafety.internal", "DL-KA032020001928"),
        ("Pooja Sharma", "+91 98801 88129", "pooja.s@fleetsafety.internal", "DL-KA532023008912"),
    ]

    for name, phone, email, lic in default_drivers:
        row = conn.execute("SELECT driver_id FROM drivers WHERE name = ?", (name,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO drivers (name, face_embedding, created_at, phone, email, license_no) VALUES (?, ?, ?, ?, ?, ?)",
                (name, dummy_emb, now, phone, email, lic),
            )

    default_vehicles = [
        ("KA-01-MJ-8821", "Tata Prima 4028.S", "Heavy Haul"),
        ("KA-04-E-4412", "Ashok Leyland 2820", "Cargo"),
        ("KA-51-AB-1904", "BharatBenz 3528C", "Heavy Haul"),
        ("KA-03-AA-9081", "Eicher Pro 3019", "Tanker"),
        ("KA-53-M-3329", "Tata Signa 4825.TK", "Heavy Haul"),
    ]

    for reg, model, vtype in default_vehicles:
        row = conn.execute("SELECT vehicle_id FROM vehicles WHERE registration_number = ?", (reg,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO vehicles (registration_number, model, vehicle_type, created_at) VALUES (?, ?, ?, ?)",
                (reg, model, vtype, now),
            )

    conn.commit()



