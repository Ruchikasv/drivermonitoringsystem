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
    face_embedding: Optional[np.ndarray]
    created_at: str
    phone: Optional[str] = None
    email: Optional[str] = None
    license_no: Optional[str] = None
    owner_id: Optional[int] = None
    is_active: int = 1
    deleted_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _serialize_embedding(embedding: np.ndarray) -> bytes:
    """Convert a numpy embedding to raw bytes for BLOB storage."""
    return embedding.astype(np.float32).tobytes()


def _deserialize_embedding(blob: bytes | None) -> Optional[np.ndarray]:
    """Reconstruct a numpy embedding from a BLOB."""
    if blob is None or len(blob) == 0:
        return None
    return np.frombuffer(blob, dtype=np.float32).copy()


def _row_to_driver_record(row: Any) -> DriverRecord:
    """Safely map a Row/dict to a DriverRecord."""
    keys = row.keys() if hasattr(row, "keys") else []
    emb_raw = row["face_embedding"] if "face_embedding" in keys else None
    return DriverRecord(
        driver_id=row["driver_id"],
        name=row["name"],
        face_embedding=_deserialize_embedding(emb_raw),
        created_at=row["created_at"],
        phone=row["phone"] if "phone" in keys else None,
        email=row["email"] if "email" in keys else None,
        license_no=row["license_no"] if "license_no" in keys else None,
        owner_id=row["owner_id"] if "owner_id" in keys else None,
        is_active=row["is_active"] if "is_active" in keys else 1,
        deleted_at=row["deleted_at"] if "deleted_at" in keys else None,
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class DriverRepository:
    """
    CRUD operations for the ``drivers`` table with owner-level isolation.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    # -- Create ---------------------------------------------------------------

    def add_driver(
        self,
        name: str,
        embedding: np.ndarray,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        license_no: Optional[str] = None,
        owner_id: Optional[int] = None,
    ) -> int:
        """Insert a new driver record for an optional owner."""
        if embedding.shape != (settings.EMBEDDING_DIM,):
            raise ValueError(
                f"Expected embedding shape ({settings.EMBEDDING_DIM},), "
                f"got {embedding.shape}"
            )

        created_at = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            INSERT INTO drivers (name, face_embedding, created_at, phone, email, license_no, owner_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (name.strip(), _serialize_embedding(embedding), created_at, phone, email, license_no, owner_id),
        )
        self._conn.commit()
        return cursor.lastrowid

    # -- Read -----------------------------------------------------------------

    def get_driver_by_id(self, driver_id: int, owner_id: Optional[int] = None) -> Optional[DriverRecord]:
        """Fetch a single active driver by primary key, scoped strictly by owner if provided."""
        if owner_id is not None:
            row = self._conn.execute(
                """
                SELECT * FROM drivers
                WHERE driver_id = ? AND is_active = 1 AND owner_id = ?
                """,
                (driver_id, owner_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM drivers WHERE driver_id = ? AND is_active = 1",
                (driver_id,),
            ).fetchone()

        if row is None:
            return None

        return _row_to_driver_record(row)

    def get_all_drivers(self, owner_id: Optional[int] = None) -> list[DriverRecord]:
        """Return all active registered drivers, strictly filtered by owner if provided."""
        if owner_id is not None:
            rows = self._conn.execute(
                """
                SELECT * FROM drivers
                WHERE is_active = 1 AND owner_id = ?
                ORDER BY driver_id
                """,
                (owner_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM drivers WHERE is_active = 1 ORDER BY driver_id"
            ).fetchall()

        return [_row_to_driver_record(row) for row in rows]

    def get_driver_count(self, owner_id: Optional[int] = None) -> int:
        """Return the total number of active registered drivers for an owner."""
        if owner_id is not None:
            row = self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM drivers WHERE is_active = 1 AND owner_id = ?",
                (owner_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM drivers WHERE is_active = 1"
            ).fetchone()
        return row["cnt"]

    # -- Update Profile -------------------------------------------------------

    def update_driver_profile(
        self,
        driver_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        license_no: Optional[str] = None,
        owner_id: Optional[int] = None,
    ) -> bool:
        """Update driver profile metadata without touching biometric embeddings."""
        existing = self.get_driver_by_id(driver_id, owner_id=owner_id)
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
            WHERE driver_id = ? AND is_active = 1
            """,
            (updated_name, updated_phone, updated_email, updated_license, driver_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Delete & Biometric Eradication ----------------------------------------

    def delete_driver(self, driver_id: int, owner_id: Optional[int] = None) -> bool:
        """
        Permanently deactivate a driver from the active fleet and permanently erase
        their biometric face embedding for privacy, while preserving historical audit logs.
        """
        import os
        from app.config import settings

        existing = self.get_driver_by_id(driver_id, owner_id=owner_id)
        if existing is None:
            return False

        now = datetime.now(timezone.utc).isoformat()

        # 1. Unassign any active vehicle
        try:
            self._conn.execute(
                """
                UPDATE driver_vehicle_assignments
                SET unassigned_at = ?
                WHERE driver_id = ? AND unassigned_at IS NULL
                """,
                (now, driver_id),
            )
        except Exception:
            pass

        # 2. Interrupt any ongoing active monitoring sessions
        try:
            self._conn.execute(
                """
                UPDATE monitoring_sessions
                SET status = 'INTERRUPTED', end_time = ?
                WHERE driver_id = ? AND status = 'ACTIVE'
                """,
                (now, driver_id),
            )
        except Exception:
            pass

        # 3. Clean up physical evidence screenshot files if needed
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

        # 4. Wipe biometric face_embedding and mark is_active = 0 with deleted_at timestamp
        cursor = self._conn.execute(
            """
            UPDATE drivers
            SET is_active = 0,
                face_embedding = NULL,
                deleted_at = ?
            WHERE driver_id = ?
            """,
            (now, driver_id),
        )

        # 5. Clean up safety ratings
        try:
            self._conn.execute("DELETE FROM driver_safety_ratings WHERE driver_id = ?", (driver_id,))
        except Exception:
            pass

        self._conn.commit()
        return cursor.rowcount > 0


