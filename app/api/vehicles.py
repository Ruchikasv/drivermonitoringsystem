from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.connection import get_connection
from app.database.vehicle_repository import VehicleRepository

router = APIRouter(tags=["Vehicles"])


class VehicleCreate(BaseModel):
    registration_number: str
    model: str
    vehicle_type: str


class VehicleUpdate(BaseModel):
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
            "assigned_driver": None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.get("/vehicles")
def get_vehicles():
    conn = get_connection()

    try:
        repo = VehicleRepository(conn)
        vehicles = repo.get_all_vehicles_with_assignments()

        return vehicles

    finally:
        conn.close()


@router.put("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: int, vehicle: VehicleUpdate):
    conn = get_connection()

    try:
        repo = VehicleRepository(conn)
        updated = repo.update_vehicle(
            vehicle_id=vehicle_id,
            registration_number=vehicle.registration_number,
            model=vehicle.model,
            vehicle_type=vehicle.vehicle_type,
        )

        # Get assignment metadata
        all_v = repo.get_all_vehicles_with_assignments()
        assigned_driver = None
        for v in all_v:
            if v["vehicle_id"] == vehicle_id:
                assigned_driver = v.get("assigned_driver")
                break

        return {
            "vehicle_id": updated.vehicle_id,
            "registration_number": updated.registration_number,
            "model": updated.model,
            "vehicle_type": updated.vehicle_type,
            "created_at": updated.created_at,
            "assigned_driver": assigned_driver,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: int):
    conn = get_connection()

    try:
        repo = VehicleRepository(conn)
        repo.delete_vehicle(vehicle_id)
        return {"success": True, "message": "Vehicle deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.delete("/drivers/{driver_id}/vehicle")
def unassign_vehicle(driver_id: int):
    conn = get_connection()

    try:
        repo = VehicleRepository(conn)
        unassigned = repo.unassign_vehicle(driver_id)
        return {
            "success": unassigned,
            "driver_id": driver_id,
            "message": "Vehicle unassigned successfully" if unassigned else "No active vehicle assignment found",
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