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
    phone: Optional[str] = None
    email: Optional[str] = None
    license_no: Optional[str] = None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _serialize_embedding(embedding: np.ndarray) -> bytes:
    """Convert a numpy embedding to raw bytes for SQLite BLOB storage."""
    return embedding.astype(np.float32).tobytes()


def _deserialize_embedding(blob: bytes) -> np.ndarray:
    """Reconstruct a numpy embedding from a SQLite BLOB."""
    return np.frombuffer(blob, dtype=np.float32).copy()


def _row_to_driver_record(row: sqlite3.Row) -> DriverRecord:
    """Safely map a SQLite Row to a DriverRecord."""
    keys = row.keys()
    return DriverRecord(
        driver_id=row["driver_id"],
        name=row["name"],
        face_embedding=_deserialize_embedding(row["face_embedding"]),
        created_at=row["created_at"],
        phone=row["phone"] if "phone" in keys else None,
        email=row["email"] if "email" in keys else None,
        license_no=row["license_no"] if "license_no" in keys else None,
    )


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

    def add_driver(
        self,
        name: str,
        embedding: np.ndarray,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        license_no: Optional[str] = None,
    ) -> int:
        """
        Insert a new driver record.

        Parameters
        ----------
        name : str
            Driver's display name.
        embedding : np.ndarray
            512-dimensional face embedding (float32, L2-normalised).
        phone, email, license_no : str, optional
            Optional profile metadata.

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
            "INSERT INTO drivers (name, face_embedding, created_at, phone, email, license_no) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, _serialize_embedding(embedding), created_at, phone, email, license_no),
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
            "SELECT * FROM drivers WHERE driver_id = ?",
            (driver_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_driver_record(row)

    def get_all_drivers(self) -> list[DriverRecord]:
        """Return all registered drivers."""
        rows = self._conn.execute(
            "SELECT * FROM drivers"
        ).fetchall()

        return [_row_to_driver_record(row) for row in rows]

    def get_driver_count(self) -> int:
        """Return the total number of registered drivers."""
        row = self._conn.execute("SELECT COUNT(*) AS cnt FROM drivers").fetchone()
        return row["cnt"]

    # -- Update Profile -------------------------------------------------------

    def update_driver_profile(
        self,
        driver_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        license_no: Optional[str] = None,
    ) -> bool:
        """
        Update driver profile metadata without touching biometric embeddings.

        Parameters
        ----------
        driver_id : int
            Target driver ID.
        name : str, optional
            Updated driver full name.
        phone, email, license_no : str, optional
            Updated profile fields.

        Returns
        -------
        bool
            ``True`` if driver existed and was updated, ``False`` otherwise.
        """
        existing = self.get_driver_by_id(driver_id)
        if existing is None:
            return False

        updated_name = name if name is not None else existing.name
        updated_phone = phone if phone is not None else existing.phone
        updated_email = email if email is not None else existing.email
        updated_license = license_no if license_no is not None else existing.license_no

        cursor = self._conn.execute(
            """
            UPDATE drivers
            SET name = ?, phone = ?, email = ?, license_no = ?
            WHERE driver_id = ?
            """,
            (updated_name, updated_phone, updated_email, updated_license, driver_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Delete ---------------------------------------------------------------

    def delete_driver(self, driver_id: int) -> bool:
        """
        Delete a driver by ID and clean up all associated foreign-key records
        (monitoring sessions, incidents, safety ratings, vehicle assignments)
        as well as physical screenshot files on disk.
        """
        import os
        from app.config import settings

        # 1. Clean up physical evidence screenshot files for this driver's incidents
        try:
            incidents = self._conn.execute(
                "SELECT evidence_path FROM monitoring_incidents WHERE driver_id = ? AND evidence_path IS NOT NULL",
                (driver_id,),
            ).fetchall()
            for inc in incidents:
                path = inc["evidence_path"]
                if path:
                    full_path = os.path.join(str(settings.PROJECT_ROOT), path)
                    if os.path.exists(full_path):
                        try:
                            os.remove(full_path)
                        except Exception:
                            pass
        except Exception:
            pass

        # 2. Delete linked table records in correct dependency order
        try:
            self._conn.execute(
                "DELETE FROM monitoring_incidents WHERE driver_id = ? OR session_id IN (SELECT session_id FROM monitoring_sessions WHERE driver_id = ?)",
                (driver_id, driver_id),
            )
            self._conn.execute("DELETE FROM driver_safety_ratings WHERE driver_id = ?", (driver_id,))
            self._conn.execute("DELETE FROM monitoring_sessions WHERE driver_id = ?", (driver_id,))
            self._conn.execute("DELETE FROM driver_vehicle_assignments WHERE driver_id = ?", (driver_id,))
        except Exception:
            pass

        # 3. Delete driver row
        cursor = self._conn.execute(
            "DELETE FROM drivers WHERE driver_id = ?",
            (driver_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

