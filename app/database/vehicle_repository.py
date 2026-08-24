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
    CRUD operations for vehicles and driver-vehicle assignments.

    Parameters
    ----------
    conn : sqlite3.Connection
        An initialised database connection.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- Vehicle creation ----------------------------------------------------

    def add_vehicle(
        self,
        registration_number: str,
        model: str,
        vehicle_type: str,
    ) -> int:
        """
        Add a vehicle to the fleet.

        Returns
        -------
        int
            The newly created vehicle ID.

        Raises
        ------
        ValueError
            If a vehicle with the same registration number already exists.
        """
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
            WHERE registration_number = ?
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
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                registration_number,
                model,
                vehicle_type,
                created_at,
            ),
        )

        self._conn.commit()

        return cursor.lastrowid  # type: ignore[return-value]

    # -- Vehicle reads -------------------------------------------------------

    def get_vehicle_by_id(
        self,
        vehicle_id: int,
    ) -> Optional[VehicleRecord]:
        """Return a vehicle by ID, or None if it does not exist."""

        row = self._conn.execute(
            """
            SELECT *
            FROM vehicles
            WHERE vehicle_id = ?
            """,
            (vehicle_id,),
        ).fetchone()

        if row is None:
            return None

        return VehicleRecord(
            vehicle_id=row["vehicle_id"],
            registration_number=row["registration_number"],
            model=row["model"],
            vehicle_type=row["vehicle_type"],
            created_at=row["created_at"],
        )

    def get_all_vehicles(self) -> list[VehicleRecord]:
        """Return all vehicles in the fleet."""

        rows = self._conn.execute(
            """
            SELECT *
            FROM vehicles
            ORDER BY registration_number
            """
        ).fetchall()

        return [
            VehicleRecord(
                vehicle_id=row["vehicle_id"],
                registration_number=row["registration_number"],
                model=row["model"],
                vehicle_type=row["vehicle_type"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_all_vehicles_with_assignments(self) -> list[dict]:
        """Return all vehicles in the fleet along with their current active driver assignment."""
        rows = self._conn.execute(
            """
            SELECT 
                v.vehicle_id,
                v.registration_number,
                v.model,
                v.vehicle_type,
                v.created_at,
                a.driver_id AS assigned_driver_id,
                d.name AS assigned_driver_name
            FROM vehicles v
            LEFT JOIN driver_vehicle_assignments a
                ON v.vehicle_id = a.vehicle_id AND a.unassigned_at IS NULL
            LEFT JOIN drivers d
                ON a.driver_id = d.driver_id
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
    ) -> VehicleRecord:
        """Update vehicle details."""
        registration_number = registration_number.strip()
        model = model.strip()
        vehicle_type = vehicle_type.strip()

        if not registration_number:
            raise ValueError("Registration number cannot be empty.")
        if not model:
            raise ValueError("Vehicle model cannot be empty.")
        if not vehicle_type:
            raise ValueError("Vehicle type cannot be empty.")

        existing_v = self.get_vehicle_by_id(vehicle_id)
        if existing_v is None:
            raise ValueError(f"Vehicle ID {vehicle_id} does not exist.")

        dup = self._conn.execute(
            """
            SELECT vehicle_id
            FROM vehicles
            WHERE registration_number = ? AND vehicle_id != ?
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

        updated = self.get_vehicle_by_id(vehicle_id)
        if updated is None:
            raise ValueError("Updated vehicle not found.")
        return updated

    def delete_vehicle(self, vehicle_id: int) -> bool:
        """Delete a vehicle if it is not currently assigned to any driver."""
        vehicle = self.get_vehicle_by_id(vehicle_id)
        if vehicle is None:
            raise ValueError(f"Vehicle ID {vehicle_id} does not exist.")

        active_assignment = self._conn.execute(
            """
            SELECT a.driver_id, d.name
            FROM driver_vehicle_assignments a
            LEFT JOIN drivers d ON a.driver_id = d.driver_id
            WHERE a.vehicle_id = ? AND a.unassigned_at IS NULL
            """,
            (vehicle_id,),
        ).fetchone()

        if active_assignment is not None:
            driver_name = active_assignment["name"] or f"Driver #{active_assignment['driver_id']}"
            driver_id = active_assignment["driver_id"]
            raise ValueError(
                f"Vehicle {vehicle.registration_number} is currently assigned to {driver_name} (#{driver_id}). Remove the assignment before deleting this vehicle."
            )

        self._conn.execute(
            "DELETE FROM driver_vehicle_assignments WHERE vehicle_id = ?",
            (vehicle_id,),
        )

        self._conn.execute(
            "DELETE FROM vehicles WHERE vehicle_id = ?",
            (vehicle_id,),
        )
        self._conn.commit()
        return True

    # -- Assignment ----------------------------------------------------------

    def assign_vehicle(
        self,
        driver_id: int,
        vehicle_id: int,
    ) -> int:
        """
        Assign a vehicle to a driver.

        If the vehicle or driver already has an active vehicle assignment,
        that assignment is closed before the new assignment is created.

        Returns
        -------
        int
            The newly created assignment ID.

        Raises
        ------
        ValueError
            If the driver or vehicle does not exist.
        """

        driver = self._conn.execute(
            """
            SELECT driver_id
            FROM drivers
            WHERE driver_id = ?
            """,
            (driver_id,),
        ).fetchone()

        if driver is None:
            raise ValueError(f"Driver ID {driver_id} does not exist.")

        vehicle = self._conn.execute(
            """
            SELECT vehicle_id
            FROM vehicles
            WHERE vehicle_id = ?
            """,
            (vehicle_id,),
        ).fetchone()

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
                unassigned_at
            )
            VALUES (?, ?, ?, NULL)
            """,
            (
                driver_id,
                vehicle_id,
                now,
            ),
        )

        self._conn.commit()

        return cursor.lastrowid  # type: ignore[return-value]

    def get_current_assignment(
        self,
        driver_id: int,
    ) -> Optional[VehicleAssignment]:
        """
        Return the driver's currently assigned vehicle.

        Returns None when the driver has no active assignment.
        """

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

    def unassign_vehicle(self, driver_id: int) -> bool:
        """
        Remove the driver's current vehicle assignment.

        Returns True if an active assignment was closed.
        """

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