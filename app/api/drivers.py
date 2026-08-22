from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.vehicle_repository import VehicleRepository
router = APIRouter(prefix="/drivers", tags=["Drivers"])


class DriverProfileUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    license_no: str | None = None


def driver_to_dict(driver, vehicle_repo):
    assignment = vehicle_repo.get_current_assignment(driver.driver_id)

    vehicle = None

    if assignment is not None:
        vehicle = {
            "vehicle_id": assignment.vehicle.vehicle_id,
            "registration_number": assignment.vehicle.registration_number,
            "model": assignment.vehicle.model,
            "vehicle_type": assignment.vehicle.vehicle_type,
            "assigned_at": assignment.assigned_at,
        }

    return {
        "driver_id": driver.driver_id,
        "name": driver.name,
        "created_at": driver.created_at,
        "phone": driver.phone,
        "email": driver.email,
        "license_no": driver.license_no,
        "isRegisteredBackend": True,
        "vehicle": vehicle,
    }


@router.get("")
def get_drivers():
    conn = get_connection()
    try:
        repo = DriverRepository(conn)
        vehicle_repo = VehicleRepository(conn)
        drivers = repo.get_all_drivers()

        return [driver_to_dict(driver, vehicle_repo) for driver in drivers]
    finally:
        conn.close()


@router.get("/{driver_id}")
def get_driver(driver_id: int):
    conn = get_connection()
    try:
        repo = DriverRepository(conn)
        vehicle_repo = VehicleRepository(conn)
        driver = repo.get_driver_by_id(driver_id)

        if driver is None:
            raise HTTPException(
                status_code=404,
                detail="Driver not found",
            )

        return driver_to_dict(driver, vehicle_repo)
    finally:
        conn.close()


@router.put("/{driver_id}/profile")
def update_driver_profile(
    driver_id: int,
    profile: DriverProfileUpdate,
):
    conn = get_connection()
    try:
        repo = DriverRepository(conn)
        vehicle_repo = VehicleRepository(conn)
        updated = repo.update_driver_profile(
            driver_id=driver_id,
            name=profile.name,
            phone=profile.phone,
            email=profile.email,
            license_no=profile.license_no,
        )

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="Driver not found",
            )

        driver = repo.get_driver_by_id(driver_id)

        return driver_to_dict(driver, vehicle_repo)
    finally:
        conn.close()