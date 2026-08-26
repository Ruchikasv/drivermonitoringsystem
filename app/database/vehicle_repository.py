"""
Repository for vehicle and driver-vehicle assignment operations.

Keeps vehicle and fleet-assignment SQL separate from driver biometric
and profile operations.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class VehicleRecord:
    """Represents a vehicle row returned from the database."""

    vehicle_id: int
    registration_number: str
    model: str
    vehicle_type: str
    created_at: str
    owner_id: Optional[int] = None
    is_active: int = 1


@dataclass
class VehicleAssignment:
    """Represents the currently active vehicle assignment for a driver."""

    assignment_id: int
    driver_id: int
    vehicle_id: int
    assigned_at: str
    unassigned_at: Optional[str]
    vehicle: VehicleRecord


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class VehicleRepository:
    """
    CRUD operations for vehicles and driver-vehicle assignments with owner-level isolation.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    # -- Vehicle creation ----------------------------------------------------

    def add_vehicle(
        self,
        registration_number: str,
        model: str,
        vehicle_type: str,
        owner_id: Optional[int] = None,
    ) -> int:
        """Add a vehicle to the fleet with optional owner association."""
        registration_number = registration_number.strip()
        model = model.strip()
        vehicle_type = vehicle_type.strip()

        if not registration_number:
            raise ValueError("Registration number cannot be empty.")
        if not model:
            raise ValueError("Vehicle model cannot be empty.")
        if not vehicle_type:
            raise ValueError("Vehicle type cannot be empty.")

        existing = self._conn.execute(
            """
            SELECT vehicle_id
            FROM vehicles
            WHERE LOWER(registration_number) = LOWER(?) AND is_active = 1
            """,
            (registration_number,),
        ).fetchone()

        if existing is not None:
            raise ValueError(
                f"Vehicle '{registration_number}' already exists."
            )

        created_at = datetime.now(timezone.utc).isoformat()

        cursor = self._conn.execute(
            """
            INSERT INTO vehicles (
                registration_number,
                model,
                vehicle_type,
                created_at,
                owner_id,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                registration_number,
                model,
                vehicle_type,
                created_at,
                owner_id,
            ),
        )

        self._conn.commit()
        return cursor.lastrowid

    # -- Vehicle reads -------------------------------------------------------

    def get_vehicle_by_id(
        self,
        vehicle_id: int,
        owner_id: Optional[int] = None,
    ) -> Optional[VehicleRecord]:
        """Return a vehicle by ID, scoped strictly by owner if provided."""
        if owner_id is not None:
            row = self._conn.execute(
                """
                SELECT *
                FROM vehicles
                WHERE vehicle_id = ? AND is_active = 1 AND owner_id = ?
                """,
                (vehicle_id, owner_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT *
                FROM vehicles
                WHERE vehicle_id = ? AND is_active = 1
                """,
                (vehicle_id,),
            ).fetchone()

        if row is None:
            return None

        keys = row.keys() if hasattr(row, "keys") else []
        return VehicleRecord(
            vehicle_id=row["vehicle_id"],
            registration_number=row["registration_number"],
            model=row["model"],
            vehicle_type=row["vehicle_type"],
            created_at=row["created_at"],
            owner_id=row["owner_id"] if "owner_id" in keys else None,
            is_active=row["is_active"] if "is_active" in keys else 1,
        )

    def get_all_vehicles(self, owner_id: Optional[int] = None) -> list[VehicleRecord]:
        """Return all active vehicles in the fleet, strictly filtered by owner if provided."""
        if owner_id is not None:
            rows = self._conn.execute(
                """
                SELECT *
                FROM vehicles
                WHERE is_active = 1 AND owner_id = ?
                ORDER BY registration_number
                """,
                (owner_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT *
                FROM vehicles
                WHERE is_active = 1
                ORDER BY registration_number
                """
            ).fetchall()

        result = []
        for row in rows:
            keys = row.keys() if hasattr(row, "keys") else []
            result.append(
                VehicleRecord(
                    vehicle_id=row["vehicle_id"],
                    registration_number=row["registration_number"],
                    model=row["model"],
                    vehicle_type=row["vehicle_type"],
                    created_at=row["created_at"],
                    owner_id=row["owner_id"] if "owner_id" in keys else None,
                    is_active=row["is_active"] if "is_active" in keys else 1,
                )
            )
        return result

    def get_all_vehicles_with_assignments(self, owner_id: Optional[int] = None) -> list[dict]:
        """Return all active vehicles along with their current driver assignment, strictly scoped by owner."""
        if owner_id is not None:
            rows = self._conn.execute(
                """
                SELECT 
                    v.vehicle_id,
                    v.registration_number,
                    v.model,
                    v.vehicle_type,
                    v.created_at,
                    v.owner_id,
                    a.driver_id AS assigned_driver_id,
                    d.name AS assigned_driver_name
                FROM vehicles v
                LEFT JOIN driver_vehicle_assignments a
                    ON v.vehicle_id = a.vehicle_id AND a.unassigned_at IS NULL
                LEFT JOIN drivers d
                    ON a.driver_id = d.driver_id AND d.is_active = 1
                WHERE v.is_active = 1 AND v.owner_id = ?
                ORDER BY v.registration_number
                """,
                (owner_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT 
                    v.vehicle_id,
                    v.registration_number,
                    v.model,
                    v.vehicle_type,
                    v.created_at,
                    v.owner_id,
                    a.driver_id AS assigned_driver_id,
                    d.name AS assigned_driver_name
                FROM vehicles v
                LEFT JOIN driver_vehicle_assignments a
                    ON v.vehicle_id = a.vehicle_id AND a.unassigned_at IS NULL
                LEFT JOIN drivers d
                    ON a.driver_id = d.driver_id AND d.is_active = 1
                WHERE v.is_active = 1
                ORDER BY v.registration_number
                """
            ).fetchall()

        result = []
        for row in rows:
            assigned_driver = None
            if row["assigned_driver_id"] is not None:
                assigned_driver = {
                    "driver_id": row["assigned_driver_id"],
                    "name": row["assigned_driver_name"] or f"Driver #{row['assigned_driver_id']}"
                }
            result.append({
                "vehicle_id": row["vehicle_id"],
                "registration_number": row["registration_number"],
                "model": row["model"],
                "vehicle_type": row["vehicle_type"],
                "created_at": row["created_at"],
                "assigned_driver": assigned_driver
            })
        return result

    def update_vehicle(
        self,
        vehicle_id: int,
        registration_number: str,
        model: str,
        vehicle_type: str,
        owner_id: Optional[int] = None,
    ) -> VehicleRecord:
        """Update vehicle details with optional owner check."""
        registration_number = registration_number.strip()
        model = model.strip()
        vehicle_type = vehicle_type.strip()

        if not registration_number:
            raise ValueError("Registration number cannot be empty.")
        if not model:
            raise ValueError("Vehicle model cannot be empty.")
        if not vehicle_type:
            raise ValueError("Vehicle type cannot be empty.")

        existing_v = self.get_vehicle_by_id(vehicle_id, owner_id=owner_id)
        if existing_v is None:
            raise ValueError(f"Vehicle ID {vehicle_id} does not exist.")

        dup = self._conn.execute(
            """
            SELECT vehicle_id
            FROM vehicles
            WHERE LOWER(registration_number) = LOWER(?) AND vehicle_id != ? AND is_active = 1
            """,
            (registration_number, vehicle_id),
        ).fetchone()

        if dup is not None:
            raise ValueError(f"Vehicle registration '{registration_number}' already exists.")

        self._conn.execute(
            """
            UPDATE vehicles
            SET registration_number = ?, model = ?, vehicle_type = ?
            WHERE vehicle_id = ?
            """,
            (registration_number, model, vehicle_type, vehicle_id),
        )
        self._conn.commit()

        updated = self.get_vehicle_by_id(vehicle_id, owner_id=owner_id)
        if updated is None:
            raise ValueError("Updated vehicle not found.")
        return updated

    def delete_vehicle(self, vehicle_id: int, owner_id: Optional[int] = None) -> bool:
        """
        Delete a vehicle with full foreign key safety, owner validation, and historical data preservation.
        1. Validates vehicle existence (raises KeyError if not found).
        2. Blocks deletion if vehicle is actively on route in an ACTIVE session (raises ValueError).
        3. Safely closes any active driver assignments.
        4. Nullifies vehicle_id on historical monitoring_sessions and incidents to preserve analytics.
        5. Deletes vehicle assignments and the vehicle row atomically.
        """
        vehicle = self.get_vehicle_by_id(vehicle_id, owner_id=owner_id)
        if vehicle is None:
            raise KeyError(f"Vehicle ID {vehicle_id} does not exist.")

        # Check if vehicle is currently in an ACTIVE monitoring session
        active_session = self._conn.execute(
            """
            SELECT session_id, driver_id
            FROM monitoring_sessions
            WHERE vehicle_id = ? AND status = 'ACTIVE' AND end_time IS NULL
            """,
            (vehicle_id,),
        ).fetchone()

        if active_session is not None:
            raise ValueError(
                f"Vehicle {vehicle.registration_number} is currently active on route in Monitoring Session #{active_session['session_id']}. Please end the active trip before deleting the vehicle."
            )

        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()

        # Safely unassign if currently assigned to a driver
        self._conn.execute(
            """
            UPDATE driver_vehicle_assignments
            SET unassigned_at = ?
            WHERE vehicle_id = ? AND unassigned_at IS NULL
            """,
            (now_iso, vehicle_id),
        )

        # Nullify foreign key references in monitoring tables so past session/incident analytics remain intact
        self._conn.execute("UPDATE monitoring_incidents SET vehicle_id = NULL WHERE vehicle_id = ?", (vehicle_id,))
        self._conn.execute("UPDATE monitoring_sessions SET vehicle_id = NULL WHERE vehicle_id = ?", (vehicle_id,))

        # Delete historical assignment links for this vehicle
        self._conn.execute("DELETE FROM driver_vehicle_assignments WHERE vehicle_id = ?", (vehicle_id,))

        # Delete vehicle row
        self._conn.execute("DELETE FROM vehicles WHERE vehicle_id = ?", (vehicle_id,))

        self._conn.commit()
        return True

    # -- Assignment ----------------------------------------------------------

    def assign_vehicle(
        self,
        driver_id: int,
        vehicle_id: int,
        owner_id: Optional[int] = None,
    ) -> int:
        """
        Assign a vehicle to a driver with strict owner validation (both must belong to owner).
        """
        if owner_id is not None:
            driver = self._conn.execute(
                """
                SELECT driver_id
                FROM drivers
                WHERE driver_id = ? AND is_active = 1 AND owner_id = ?
                """,
                (driver_id, owner_id),
            ).fetchone()
        else:
            driver = self._conn.execute(
                """
                SELECT driver_id
                FROM drivers
                WHERE driver_id = ? AND is_active = 1
                """,
                (driver_id,),
            ).fetchone()

        if driver is None:
            raise ValueError(f"Driver ID {driver_id} does not exist.")

        vehicle = self.get_vehicle_by_id(vehicle_id, owner_id=owner_id)
        if vehicle is None:
            raise ValueError(f"Vehicle ID {vehicle_id} does not exist.")

        now = datetime.now(timezone.utc).isoformat()

        # Close any active assignment for this vehicle (if assigned to another driver).
        self._conn.execute(
            """
            UPDATE driver_vehicle_assignments
            SET unassigned_at = ?
            WHERE vehicle_id = ?
              AND unassigned_at IS NULL
            """,
            (now, vehicle_id),
        )

        # Close the driver's previous active assignment, if any.
        self._conn.execute(
            """
            UPDATE driver_vehicle_assignments
            SET unassigned_at = ?
            WHERE driver_id = ?
              AND unassigned_at IS NULL
            """,
            (now, driver_id),
        )

        cursor = self._conn.execute(
            """
            INSERT INTO driver_vehicle_assignments (
                driver_id,
                vehicle_id,
                assigned_at,
                unassigned_at,
                owner_id
            )
            VALUES (?, ?, ?, NULL, ?)
            """,
            (
                driver_id,
                vehicle_id,
                now,
                owner_id,
            ),
        )

        self._conn.commit()

        return cursor.lastrowid  # type: ignore[return-value]

    def get_current_assignment(
        self,
        driver_id: int,
        owner_id: Optional[int] = None,
    ) -> Optional[VehicleAssignment]:
        """
        Return the driver's currently assigned vehicle, optionally scoped by owner.
        Returns None when the driver has no active assignment or belongs to another owner.
        """
        if owner_id is not None:
            row = self._conn.execute(
                """
                SELECT
                    a.assignment_id,
                    a.driver_id,
                    a.vehicle_id,
                    a.assigned_at,
                    a.unassigned_at,
                    v.registration_number,
                    v.model,
                    v.vehicle_type,
                    v.created_at AS vehicle_created_at
                FROM driver_vehicle_assignments a
                JOIN vehicles v
                    ON v.vehicle_id = a.vehicle_id
                JOIN drivers d
                    ON d.driver_id = a.driver_id
                WHERE a.driver_id = ?
                  AND a.unassigned_at IS NULL
                  AND d.is_active = 1
                  AND d.owner_id = ?
                ORDER BY a.assigned_at DESC
                LIMIT 1
                """,
                (driver_id, owner_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT
                    a.assignment_id,
                    a.driver_id,
                    a.vehicle_id,
                    a.assigned_at,
                    a.unassigned_at,
                    v.registration_number,
                    v.model,
                    v.vehicle_type,
                    v.created_at AS vehicle_created_at
                FROM driver_vehicle_assignments a
                JOIN vehicles v
                    ON v.vehicle_id = a.vehicle_id
                WHERE a.driver_id = ?
                  AND a.unassigned_at IS NULL
                ORDER BY a.assigned_at DESC
                LIMIT 1
                """,
                (driver_id,),
            ).fetchone()

        if row is None:
            return None

        vehicle = VehicleRecord(
            vehicle_id=row["vehicle_id"],
            registration_number=row["registration_number"],
            model=row["model"],
            vehicle_type=row["vehicle_type"],
            created_at=row["vehicle_created_at"],
        )

        return VehicleAssignment(
            assignment_id=row["assignment_id"],
            driver_id=row["driver_id"],
            vehicle_id=row["vehicle_id"],
            assigned_at=row["assigned_at"],
            unassigned_at=row["unassigned_at"],
            vehicle=vehicle,
        )

    def unassign_vehicle(self, driver_id: int, owner_id: Optional[int] = None) -> bool:
        """
        Remove the driver's current vehicle assignment, validating owner ownership.
        Returns True if an active assignment was closed.
        """
        if owner_id is not None:
            driver = self._conn.execute(
                "SELECT driver_id FROM drivers WHERE driver_id = ? AND is_active = 1 AND owner_id = ?",
                (driver_id, owner_id),
            ).fetchone()
            if driver is None:
                return False

        now = datetime.now(timezone.utc).isoformat()

        cursor = self._conn.execute(
            """
            UPDATE driver_vehicle_assignments
            SET unassigned_at = ?
            WHERE driver_id = ?
              AND unassigned_at IS NULL
            """,
            (now, driver_id),
        )

        self._conn.commit()

        return cursor.rowcount > 0

    # -- Assignment history -------------------------------------------------

    def get_assignment_history(
        self,
        driver_id: int,
    ) -> list[VehicleAssignment]:
        """Return all vehicle assignments for a driver."""

        rows = self._conn.execute(
            """
            SELECT
                a.assignment_id,
                a.driver_id,
                a.vehicle_id,
                a.assigned_at,
                a.unassigned_at,
                v.registration_number,
                v.model,
                v.vehicle_type,
                v.created_at AS vehicle_created_at
            FROM driver_vehicle_assignments a
            JOIN vehicles v
                ON v.vehicle_id = a.vehicle_id
            WHERE a.driver_id = ?
            ORDER BY a.assigned_at DESC
            """,
            (driver_id,),
        ).fetchall()

        assignments: list[VehicleAssignment] = []

        for row in rows:
            vehicle = VehicleRecord(
                vehicle_id=row["vehicle_id"],
                registration_number=row["registration_number"],
                model=row["model"],
                vehicle_type=row["vehicle_type"],
                created_at=row["vehicle_created_at"],
            )

            assignments.append(
                VehicleAssignment(
                    assignment_id=row["assignment_id"],
                    driver_id=row["driver_id"],
                    vehicle_id=row["vehicle_id"],
                    assigned_at=row["assigned_at"],
                    unassigned_at=row["unassigned_at"],
                    vehicle=vehicle,
                )
            )

        return assignments