"""
Database connection and schema management for SQLite (dev/testing) and PostgreSQL (production).

Provides factory functions for database connections, schema migrations,
and multi-tenant table initialisation.
"""

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional, Union

from app.config import settings



TABLE_PK_MAP = {
    "owners": "owner_id",
    "drivers": "driver_id",
    "vehicles": "vehicle_id",
    "monitoring_sessions": "session_id",
    "monitoring_incidents": "incident_id",
    "driver_vehicle_assignments": "assignment_id",
}



class PostgresRow(dict):
    """Row wrapper allowing both dictionary-key and integer-index access, mirroring sqlite3.Row."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        if isinstance(key, int):
            vals = list(self.values())
            return vals[key] if 0 <= key < len(vals) else default
        return super().get(key, default)


class PostgresCursorWrapper:
    """Cursor wrapper that translates SQLite SQL dialects and captures lastrowid on PostgreSQL."""

    def __init__(self, raw_cursor: Any, conn_wrapper: Any) -> None:
        self._cur = raw_cursor
        self._conn_wrapper = conn_wrapper
        self.lastrowid: Optional[int] = None
        self.rowcount: int = -1

    def execute(self, sql: str, params: Any = None) -> "PostgresCursorWrapper":
        clean_sql = sql.strip()

        # Ignore SQLite PRAGMA statements
        if clean_sql.upper().startswith("PRAGMA"):
            return self

        # Translate INSERT OR REPLACE to ON CONFLICT
        if "INSERT OR REPLACE INTO" in clean_sql.upper():
            clean_sql = re.sub(
                r"INSERT\s+OR\s+REPLACE\s+INTO\s+system_metadata\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
                r"INSERT INTO system_metadata (\1) VALUES (\2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                clean_sql,
                flags=re.IGNORECASE,
            )

        # Translate parameter placeholders from ? to %s
        clean_sql = clean_sql.replace("?", "%s")

        # Automatically append RETURNING for autoincrement primary keys if needed
        is_insert = clean_sql.upper().startswith("INSERT INTO")
        returning_pk = None
        if is_insert and "RETURNING" not in clean_sql.upper() and "ON CONFLICT" not in clean_sql.upper():
            for tbl, pk in TABLE_PK_MAP.items():
                if f"insert into {tbl}" in clean_sql.lower():
                    clean_sql += f" RETURNING {pk}"
                    returning_pk = pk
                    break


        if params is not None:
            if isinstance(params, (list, tuple)):
                self._cur.execute(clean_sql, tuple(params))
            else:
                self._cur.execute(clean_sql, params)
        else:
            self._cur.execute(clean_sql)

        self.rowcount = self._cur.rowcount

        if returning_pk:
            try:
                row = self._cur.fetchone()
                if row:
                    self.lastrowid = row[returning_pk] if isinstance(row, dict) else row[0]
            except Exception:
                self.lastrowid = None
        else:
            self.lastrowid = None

        return self

    def fetchone(self) -> Any:
        row = self._cur.fetchone()
        if row is None:
            return None
        return PostgresRow(row) if isinstance(row, dict) else row

    def fetchall(self) -> list:
        rows = self._cur.fetchall()
        return [PostgresRow(r) if isinstance(r, dict) else r for r in rows]

    def __iter__(self):
        for r in self._cur:
            yield PostgresRow(r) if isinstance(r, dict) else r

    def close(self) -> None:
        self._cur.close()



class PostgresConnectionWrapper:
    """Connection wrapper providing identical interface for SQLite and PostgreSQL."""

    def __init__(self, raw_conn: Any) -> None:
        self._conn = raw_conn

    def cursor(self) -> PostgresCursorWrapper:
        return PostgresCursorWrapper(self._conn.cursor(), self)

    def execute(self, sql: str, params: Any = None) -> PostgresCursorWrapper:
        cur = self.cursor()
        return cur.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    @property
    def info(self):
        return getattr(self._conn, "info", None)


def get_connection(db_path: Union[Path, str, None] = None) -> Any:
    """
    Create and return an active database connection.

    Supports SQLite (local development, testing) and PostgreSQL (production).
    """
    target_url = str(db_path) if db_path is not None else settings.DATABASE_URL

    if target_url.startswith("postgresql://") or target_url.startswith("postgresql+psycopg://"):
        import psycopg
        from psycopg.rows import dict_row

        # Normalize URL scheme for psycopg 3
        conn_str = target_url.replace("postgresql+psycopg://", "postgresql://")
        raw_conn = psycopg.connect(conn_str, row_factory=dict_row, connect_timeout=3)
        raw_conn.autocommit = False
        return PostgresConnectionWrapper(raw_conn)

    # SQLite connection handling
    if db_path is None:
        db_file = settings.DATABASE_PATH
    elif str(db_path) == ":memory:":
        db_file = ":memory:"
    elif str(db_path).startswith("sqlite:///"):
        db_file = str(db_path).replace("sqlite:///", "")
    else:
        db_file = str(db_path)

    if str(db_file) != ":memory:":
        file_path = Path(db_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(file_path), check_same_thread=False)
    else:
        conn = sqlite3.connect(":memory:", check_same_thread=False)

    conn.row_factory = sqlite3.Row  # Dict-like column access
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn



def init_db(conn: Any) -> None:
    """
    Create all tables and indexes if they do not exist, and safely
    apply column migrations for multi-tenant owner architecture.

    Idempotent — safe to call on startup across SQLite and PostgreSQL.
    """
    is_postgres = hasattr(conn, "info") or "psycopg" in str(type(conn)).lower()
    pk_auto = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    blob_type = "BYTEA" if is_postgres else "BLOB"

    cursor = conn.cursor() if is_postgres else conn

    # 1. System Metadata
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS system_metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    # 2. Owners / Fleet Managers
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS owners (
            owner_id       {pk_auto},
            name           TEXT    NOT NULL,
            email          TEXT    NOT NULL UNIQUE,
            password_hash  TEXT    NOT NULL,
            created_at     TEXT    NOT NULL,
            is_active      INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_owners_email_lower
        ON owners (LOWER(email))
        """
    )

    # 3. Drivers
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS drivers (
            driver_id       {pk_auto},
            owner_id        INTEGER REFERENCES owners(owner_id),
            name            TEXT    NOT NULL,
            face_embedding  {blob_type},
            created_at      TEXT    NOT NULL,
            phone           TEXT,
            email           TEXT,
            license_no      TEXT,
            is_active       INTEGER NOT NULL DEFAULT 1,
            deleted_at      TEXT
        )
        """
    )

    # 4. Vehicles
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS vehicles (
            vehicle_id           {pk_auto},
            owner_id             INTEGER REFERENCES owners(owner_id),
            registration_number  TEXT    NOT NULL UNIQUE,
            model                TEXT    NOT NULL,
            vehicle_type         TEXT    NOT NULL,
            created_at           TEXT    NOT NULL,
            is_active            INTEGER NOT NULL DEFAULT 1,
            deleted_at           TEXT
        )
        """
    )

    # 5. Driver Vehicle Assignments
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS driver_vehicle_assignments (
            assignment_id   {pk_auto},
            owner_id        INTEGER REFERENCES owners(owner_id),
            driver_id       INTEGER NOT NULL REFERENCES drivers(driver_id),
            vehicle_id      INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
            assigned_at     TEXT    NOT NULL,
            unassigned_at   TEXT
        )
        """
    )

    # 6. Monitoring Sessions
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS monitoring_sessions (
            session_id           {pk_auto},
            owner_id             INTEGER REFERENCES owners(owner_id),
            driver_id            INTEGER NOT NULL REFERENCES drivers(driver_id),
            vehicle_id           INTEGER REFERENCES vehicles(vehicle_id),
            session_token        TEXT UNIQUE,
            start_time           TEXT    NOT NULL,
            end_time             TEXT,
            status               TEXT    NOT NULL DEFAULT 'ACTIVE',
            pause_started_at     TEXT,
            total_paused_seconds REAL    NOT NULL DEFAULT 0.0
        )
        """
    )

    # 7. Monitoring Incidents
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS monitoring_incidents (
            incident_id    {pk_auto},
            session_id     INTEGER NOT NULL REFERENCES monitoring_sessions(session_id),
            owner_id       INTEGER REFERENCES owners(owner_id),
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
            evidence_path  TEXT
        )
        """
    )

    # 8. Driver Safety Ratings
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS driver_safety_ratings (
            rating_id          {pk_auto},
            driver_id          INTEGER NOT NULL UNIQUE REFERENCES drivers(driver_id),
            owner_id           INTEGER REFERENCES owners(owner_id),
            safety_score       REAL,
            total_sessions     INTEGER DEFAULT 0,
            total_incidents    INTEGER DEFAULT 0,
            critical_incidents INTEGER DEFAULT 0,
            last_updated       TEXT    NOT NULL
        )
        """
    )

    # Idempotent Column Migrations for SQLite
    if not is_postgres:
        d_cols = {row["name"] for row in cursor.execute("PRAGMA table_info(drivers)").fetchall()}
        for col, ctype in [("owner_id", "INTEGER"), ("phone", "TEXT"), ("email", "TEXT"), ("license_no", "TEXT"), ("is_active", "INTEGER NOT NULL DEFAULT 1"), ("deleted_at", "TEXT")]:
            if col not in d_cols:
                cursor.execute(f"ALTER TABLE drivers ADD COLUMN {col} {ctype}")

        v_cols = {row["name"] for row in cursor.execute("PRAGMA table_info(vehicles)").fetchall()}
        for col, ctype in [("owner_id", "INTEGER"), ("is_active", "INTEGER NOT NULL DEFAULT 1"), ("deleted_at", "TEXT")]:
            if col not in v_cols:
                cursor.execute(f"ALTER TABLE vehicles ADD COLUMN {col} {ctype}")

        a_cols = {row["name"] for row in cursor.execute("PRAGMA table_info(driver_vehicle_assignments)").fetchall()}
        if "owner_id" not in a_cols:
            cursor.execute("ALTER TABLE driver_vehicle_assignments ADD COLUMN owner_id INTEGER")

        s_cols = {row["name"] for row in cursor.execute("PRAGMA table_info(monitoring_sessions)").fetchall()}
        for col, ctype in [
            ("owner_id", "INTEGER"),
            ("session_token", "TEXT"),
            ("pause_started_at", "TEXT"),
            ("total_paused_seconds", "REAL NOT NULL DEFAULT 0.0"),
        ]:
            if col not in s_cols:
                cursor.execute(f"ALTER TABLE monitoring_sessions ADD COLUMN {col} {ctype}")

        inc_cols = {row["name"] for row in cursor.execute("PRAGMA table_info(monitoring_incidents)").fetchall()}
        if "owner_id" not in inc_cols:
            cursor.execute("ALTER TABLE monitoring_incidents ADD COLUMN owner_id INTEGER")

        r_cols = {row["name"] for row in cursor.execute("PRAGMA table_info(driver_safety_ratings)").fetchall()}
        if "owner_id" not in r_cols:
            cursor.execute("ALTER TABLE driver_safety_ratings ADD COLUMN owner_id INTEGER")

    # Invariant: Single ACTIVE session per driver
    cursor.execute(
        """
        UPDATE monitoring_sessions
        SET status = 'INTERRUPTED',
            end_time = COALESCE(end_time, start_time)
        WHERE status = 'ACTIVE'
          AND session_id NOT IN (
              SELECT MAX(session_id)
              FROM monitoring_sessions
              GROUP BY driver_id
          )
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_single_active_session_per_driver
        ON monitoring_sessions (driver_id)
        WHERE status = 'ACTIVE'
        """
    )

    conn.commit()


def seed_default_data(conn: Any) -> None:
    """Seed initial commercial fleet drivers and vehicles on fresh development DB only."""
    if settings.ENVIRONMENT == "production":
        return  # Production NEVER seeds mock demo records

    from datetime import datetime, timezone
    import numpy as np

    # Check if database has already completed initial seeding in the past
    row = conn.execute("SELECT value FROM system_metadata WHERE key = 'initial_seed_completed'").fetchone()
    if row is not None and (row["value"] if isinstance(row, dict) or hasattr(row, "keys") else row[0]) == "1":
        return  # NEVER re-seed or resurrect deleted drivers/vehicles

    driver_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM drivers").fetchone()["cnt"]
    vehicle_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM vehicles").fetchone()["cnt"]

    if driver_cnt > 0 or vehicle_cnt > 0:
        conn.execute("INSERT OR REPLACE INTO system_metadata (key, value) VALUES ('initial_seed_completed', '1')")
        conn.commit()
        return

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
        conn.execute(
            "INSERT INTO drivers (name, face_embedding, created_at, phone, email, license_no, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)",
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
        conn.execute(
            "INSERT INTO vehicles (registration_number, model, vehicle_type, created_at) VALUES (?, ?, ?, ?)",
            (reg, model, vtype, now),
        )

    conn.execute("INSERT OR REPLACE INTO system_metadata (key, value) VALUES ('initial_seed_completed', '1')")
    conn.commit()




