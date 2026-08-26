from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import get_current_owner
from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.owner_repository import OwnerRecord
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
def create_vehicle(
    vehicle: VehicleCreate,
    conn=Depends(get_connection),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    try:
        repo = VehicleRepository(conn)
        vehicle_id = repo.add_vehicle(
            registration_number=vehicle.registration_number,
            model=vehicle.model,
            vehicle_type=vehicle.vehicle_type,
            owner_id=current_owner.owner_id,
        )

        created = repo.get_vehicle_by_id(vehicle_id, owner_id=current_owner.owner_id)

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


@router.get("/vehicles")
def get_vehicles(
    conn=Depends(get_connection),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    repo = VehicleRepository(conn)
    vehicles = repo.get_all_vehicles_with_assignments(owner_id=current_owner.owner_id)
    return vehicles


@router.get("/vehicles/{vehicle_id}")
def get_vehicle(
    vehicle_id: int,
    conn=Depends(get_connection),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    repo = VehicleRepository(conn)
    vehicle = repo.get_vehicle_by_id(vehicle_id, owner_id=current_owner.owner_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    all_v = repo.get_all_vehicles_with_assignments(owner_id=current_owner.owner_id)
    assigned_driver = None
    for v in all_v:
        if v["vehicle_id"] == vehicle_id:
            assigned_driver = v.get("assigned_driver")
            break
    return {
        "vehicle_id": vehicle.vehicle_id,
        "registration_number": vehicle.registration_number,
        "model": vehicle.model,
        "vehicle_type": vehicle.vehicle_type,
        "created_at": vehicle.created_at,
        "assigned_driver": assigned_driver,
    }


@router.put("/vehicles/{vehicle_id}")
def update_vehicle(
    vehicle_id: int,
    vehicle: VehicleUpdate,
    conn=Depends(get_connection),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    try:
        repo = VehicleRepository(conn)
        existing = repo.get_vehicle_by_id(vehicle_id, owner_id=current_owner.owner_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        updated = repo.update_vehicle(
            vehicle_id=vehicle_id,
            registration_number=vehicle.registration_number,
            model=vehicle.model,
            vehicle_type=vehicle.vehicle_type,
            owner_id=current_owner.owner_id,
        )

        all_v = repo.get_all_vehicles_with_assignments(owner_id=current_owner.owner_id)
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
    except HTTPException:
        raise
    except ValueError as e:
        if "does not exist" in str(e).lower() or "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    conn=Depends(get_connection),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    try:
        repo = VehicleRepository(conn)
        repo.delete_vehicle(vehicle_id, owner_id=current_owner.owner_id)
        return {"success": True, "message": f"Vehicle #{vehicle_id} deleted successfully"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'\""))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete vehicle #{vehicle_id}: {e}")


@router.post("/drivers/{driver_id}/vehicle")
def assign_vehicle(
    driver_id: int,
    assignment: VehicleAssignment,
    conn=Depends(get_connection),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    try:
        d_repo = DriverRepository(conn)
        driver = d_repo.get_driver_by_id(driver_id, owner_id=current_owner.owner_id)
        if driver is None:
            raise HTTPException(status_code=404, detail=f"Driver #{driver_id} not found")

        repo = VehicleRepository(conn)
        vehicle = repo.get_vehicle_by_id(assignment.vehicle_id, owner_id=current_owner.owner_id)
        if vehicle is None:
            raise HTTPException(status_code=404, detail=f"Vehicle #{assignment.vehicle_id} not found")

        assignment_id = repo.assign_vehicle(
            driver_id=driver_id,
            vehicle_id=assignment.vehicle_id,
            owner_id=current_owner.owner_id,
        )

        current = repo.get_current_assignment(driver_id, owner_id=current_owner.owner_id)

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
    except HTTPException:
        raise
    except ValueError as e:
        if "does not exist" in str(e).lower() or "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/drivers/{driver_id}/vehicle")
def unassign_vehicle(
    driver_id: int,
    conn=Depends(get_connection),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    d_repo = DriverRepository(conn)
    driver = d_repo.get_driver_by_id(driver_id, owner_id=current_owner.owner_id)
    if driver is None:
        raise HTTPException(status_code=404, detail=f"Driver #{driver_id} not found")

    repo = VehicleRepository(conn)
    unassigned = repo.unassign_vehicle(driver_id, owner_id=current_owner.owner_id)
    return {
        "success": unassigned,
        "driver_id": driver_id,
        "message": "Vehicle unassigned successfully" if unassigned else "No active vehicle assignment found",
    }


@router.get("/drivers/{driver_id}/vehicle")
def get_driver_vehicle(
    driver_id: int,
    conn=Depends(get_connection),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    d_repo = DriverRepository(conn)
    driver = d_repo.get_driver_by_id(driver_id, owner_id=current_owner.owner_id)
    if driver is None:
        raise HTTPException(status_code=404, detail=f"Driver #{driver_id} not found")

    repo = VehicleRepository(conn)
    current = repo.get_current_assignment(driver_id, owner_id=current_owner.owner_id)

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
