from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.connection import get_connection
from app.database.vehicle_repository import VehicleRepository

router = APIRouter(tags=["Vehicles"])


class VehicleCreate(BaseModel):
    registration_number: str
    model: str
    vehicle_type: str


class VehicleAssignment(BaseModel):
    vehicle_id: int


@router.post("/vehicles")
def create_vehicle(vehicle: VehicleCreate):
    conn = get_connection()

    try:
        repo = VehicleRepository(conn)

        vehicle_id = repo.add_vehicle(
            registration_number=vehicle.registration_number,
            model=vehicle.model,
            vehicle_type=vehicle.vehicle_type,
        )

        created = repo.get_vehicle_by_id(vehicle_id)

        return {
            "vehicle_id": created.vehicle_id,
            "registration_number": created.registration_number,
            "model": created.model,
            "vehicle_type": created.vehicle_type,
            "created_at": created.created_at,
        }

    finally:
        conn.close()


@router.get("/vehicles")
def get_vehicles():
    conn = get_connection()

    try:
        repo = VehicleRepository(conn)
        vehicles = repo.get_all_vehicles()

        return [
            {
                "vehicle_id": v.vehicle_id,
                "registration_number": v.registration_number,
                "model": v.model,
                "vehicle_type": v.vehicle_type,
                "created_at": v.created_at,
            }
            for v in vehicles
        ]

    finally:
        conn.close()


@router.post("/drivers/{driver_id}/vehicle")
def assign_vehicle(
    driver_id: int,
    assignment: VehicleAssignment,
):
    conn = get_connection()

    try:
        repo = VehicleRepository(conn)

        assignment_id = repo.assign_vehicle(
            driver_id=driver_id,
            vehicle_id=assignment.vehicle_id,
        )

        current = repo.get_current_assignment(driver_id)

        if current is None:
            raise HTTPException(
                status_code=404,
                detail="Vehicle assignment could not be retrieved",
            )

        return {
            "assignment_id": assignment_id,
            "driver_id": current.driver_id,
            "vehicle_id": current.vehicle_id,
            "registration_number": current.vehicle.registration_number,
            "model": current.vehicle.model,
            "vehicle_type": current.vehicle.vehicle_type,
            "assigned_at": current.assigned_at,
        }

    finally:
        conn.close()


@router.get("/drivers/{driver_id}/vehicle")
def get_driver_vehicle(driver_id: int):
    conn = get_connection()

    try:
        repo = VehicleRepository(conn)

        current = repo.get_current_assignment(driver_id)

        if current is None:
            return {
                "assigned": False,
                "vehicle": None,
            }

        return {
            "assigned": True,
            "vehicle": {
                "vehicle_id": current.vehicle.vehicle_id,
                "registration_number": current.vehicle.registration_number,
                "model": current.vehicle.model,
                "vehicle_type": current.vehicle.vehicle_type,
            },
            "assignment_id": current.assignment_id,
            "assigned_at": current.assigned_at,
        }

    finally:
        conn.close()