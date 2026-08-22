"""
Repository for driver CRUD operations.

Encapsulates all SQL queries related to the ``drivers`` table,
keeping database logic out of application code.  Embeddings are
serialised as raw float32 bytes (compact, safe, portable).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from app.config import settings


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class DriverRecord:
    """Represents a driver row returned from the database."""

    driver_id: int
    name: str
    face_embedding: np.ndarray
    created_at: str


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _serialize_embedding(embedding: np.ndarray) -> bytes:
    """Convert a numpy embedding to raw bytes for SQLite BLOB storage."""
    return embedding.astype(np.float32).tobytes()


def _deserialize_embedding(blob: bytes) -> np.ndarray:
    """Reconstruct a numpy embedding from a SQLite BLOB."""
    return np.frombuffer(blob, dtype=np.float32).copy()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class DriverRepository:
    """
    CRUD operations for the ``drivers`` table.

    Parameters
    ----------
    conn : sqlite3.Connection
        An initialised database connection (schema already created).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- Create ---------------------------------------------------------------

    def add_driver(self, name: str, embedding: np.ndarray) -> int:
        """
        Insert a new driver record.

        Parameters
        ----------
        name : str
            Driver's display name.
        embedding : np.ndarray
            512-dimensional face embedding (float32, L2-normalised).

        Returns
        -------
        int
            The auto-generated ``driver_id``.

        Raises
        ------
        ValueError
            If the embedding has an unexpected shape.
        """
        if embedding.shape != (settings.EMBEDDING_DIM,):
            raise ValueError(
                f"Expected embedding shape ({settings.EMBEDDING_DIM},), "
                f"got {embedding.shape}"
            )

        created_at = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "INSERT INTO drivers (name, face_embedding, created_at) VALUES (?, ?, ?)",
            (name, _serialize_embedding(embedding), created_at),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    # -- Read -----------------------------------------------------------------

    def get_driver_by_id(self, driver_id: int) -> Optional[DriverRecord]:
        """
        Fetch a single driver by primary key.

        Returns ``None`` if the driver does not exist.
        """
        row = self._conn.execute(
            "SELECT driver_id, name, face_embedding, created_at "
            "FROM drivers WHERE driver_id = ?",
            (driver_id,),
        ).fetchone()

        if row is None:
            return None

        return DriverRecord(
            driver_id=row["driver_id"],
            name=row["name"],
            face_embedding=_deserialize_embedding(row["face_embedding"]),
            created_at=row["created_at"],
        )

    def get_all_drivers(self) -> list[DriverRecord]:
        """Return all registered drivers."""
        rows = self._conn.execute(
            "SELECT driver_id, name, face_embedding, created_at FROM drivers"
        ).fetchall()

        return [
            DriverRecord(
                driver_id=row["driver_id"],
                name=row["name"],
                face_embedding=_deserialize_embedding(row["face_embedding"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_driver_count(self) -> int:
        """Return the total number of registered drivers."""
        row = self._conn.execute("SELECT COUNT(*) AS cnt FROM drivers").fetchone()
        return row["cnt"]

    # -- Delete ---------------------------------------------------------------

    def delete_driver(self, driver_id: int) -> bool:
        """
        Delete a driver by ID.

        Returns
        -------
        bool
            ``True`` if a row was deleted, ``False`` if the ID was not found.
        """
        cursor = self._conn.execute(
            "DELETE FROM drivers WHERE driver_id = ?",
            (driver_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0
