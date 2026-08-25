from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.vehicle_repository import VehicleRepository
from app.database.monitoring_repository import MonitoringRepository

router = APIRouter(prefix="/drivers", tags=["Drivers"])


class DriverProfileUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    license_no: str | None = None


def _get_repos(conn=Depends(get_connection)):
    yield conn, DriverRepository(conn), VehicleRepository(conn), MonitoringRepository(conn)


def driver_to_dict(driver, vehicle_repo, monitoring_repo):
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

    # Determine driver status strictly from genuine active monitoring sessions
    active_session = monitoring_repo.get_active_session_by_driver(driver.driver_id)
    status = "ON_ROUTE" if active_session is not None else "OFF_DUTY"

    # Compute real metrics from monitoring DB
    safety_rating = monitoring_repo.get_safety_rating(driver.driver_id)
    safety_score = safety_rating.safety_score if safety_rating else None
    total_sessions = safety_rating.total_sessions if safety_rating else 0
    total_incidents = safety_rating.total_incidents if safety_rating else 0

    # Compute driving hours from completed sessions
    try:
        rows = monitoring_repo._conn.execute(
            """SELECT start_time, end_time FROM monitoring_sessions
               WHERE driver_id = ? AND end_time IS NOT NULL""",
            (driver.driver_id,),
        ).fetchall()
        total_seconds = 0
        for row in rows:
            from datetime import datetime
            try:
                start = datetime.fromisoformat(row["start_time"])
                end = datetime.fromisoformat(row["end_time"])
                total_seconds += max(0, (end - start).total_seconds())
            except Exception:
                pass
        driving_hours = round(total_seconds / 3600.0, 1)
    except Exception:
        driving_hours = None

    return {
        "driver_id": driver.driver_id,
        "name": driver.name,
        "created_at": driver.created_at,
        "phone": driver.phone,
        "email": driver.email,
        "license_no": driver.license_no,
        "isRegisteredBackend": True,
        "status": status,
        "vehicle": vehicle,
        "safety_score": safety_score,
        "total_trips": total_sessions,
        "driving_hours": driving_hours,
        "drowsiness_events": total_incidents,
        "alcohol_events": 0,  # MQ-3 sensor not yet integrated
    }


@router.get("")
def get_drivers(repos=Depends(_get_repos)):
    conn, repo, vehicle_repo, monitoring_repo = repos
    drivers = repo.get_all_drivers()
    return [driver_to_dict(driver, vehicle_repo, monitoring_repo) for driver in drivers]


@router.get("/{driver_id}")
def get_driver(driver_id: int, repos=Depends(_get_repos)):
    conn, repo, vehicle_repo, monitoring_repo = repos
    driver = repo.get_driver_by_id(driver_id)
    if driver is None:
        raise HTTPException(
            status_code=404,
            detail="Driver not found",
        )
    return driver_to_dict(driver, vehicle_repo, monitoring_repo)


@router.put("/{driver_id}/profile")
def update_driver_profile(
    driver_id: int,
    profile: DriverProfileUpdate,
    repos=Depends(_get_repos),
):
    conn, repo, vehicle_repo, monitoring_repo = repos
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
    return driver_to_dict(driver, vehicle_repo, monitoring_repo)