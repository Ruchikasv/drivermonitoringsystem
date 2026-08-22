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

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # Access columns by name.
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent-read perf.
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """
    Create database tables if they do not already exist.

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
            created_at      TEXT    NOT NULL
        )
        """
    )
    conn.commit()
