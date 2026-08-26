from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import get_current_owner
from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.owner_repository import OwnerRecord
from app.database.vehicle_repository import VehicleRepository

router = APIRouter(prefix="/drivers", tags=["Drivers"])


class DriverProfileUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    license_no: str | None = None


def _get_repos(conn=Depends(get_connection)):
    yield conn, DriverRepository(conn), VehicleRepository(conn), MonitoringRepository(conn)


def driver_to_dict(driver, vehicle_repo, monitoring_repo):
    assignment = vehicle_repo.get_current_assignment(driver.driver_id, owner_id=driver.owner_id)

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
    active_session = monitoring_repo.get_active_session_by_driver(driver.driver_id, owner_id=driver.owner_id)
    status = "ON_ROUTE" if active_session is not None else "OFF_DUTY"

    # Compute real metrics from monitoring DB
    safety_rating = monitoring_repo.get_safety_rating(driver.driver_id, owner_id=driver.owner_id)
    safety_score = safety_rating.safety_score if safety_rating else None
    total_sessions = safety_rating.total_sessions if safety_rating else 0
    total_incidents = safety_rating.total_incidents if safety_rating else 0

    # Compute driving hours from all sessions (completed + active), excluding paused time
    try:
        rows = monitoring_repo._conn.execute(
            """SELECT start_time, end_time, status, pause_started_at, total_paused_seconds FROM monitoring_sessions
               WHERE driver_id = ?""",
            (driver.driver_id,),
        ).fetchall()
        total_seconds = 0.0
        for row in rows:
            from datetime import datetime, timezone
            try:
                start = datetime.fromisoformat(row["start_time"])
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if row["end_time"]:
                    end = datetime.fromisoformat(row["end_time"])
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=timezone.utc)
                else:
                    end = datetime.now(timezone.utc)
                dur = max(0.0, (end - start).total_seconds())
                paused = float(row["total_paused_seconds"] or 0.0)
                if row["status"] == "PAUSED" and row["pause_started_at"]:
                    p_start = datetime.fromisoformat(row["pause_started_at"])
                    if p_start.tzinfo is None:
                        p_start = p_start.replace(tzinfo=timezone.utc)
                    paused += max(0.0, (end - p_start).total_seconds())
                active_dur = max(0.0, dur - paused)
                total_seconds += active_dur
            except Exception:
                pass
        driving_hours = round(total_seconds / 3600.0, 1)
    except Exception:
        driving_hours = 0.0

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
        "alcohol_events": 0,
    }


@router.get("")
def get_drivers(repos=Depends(_get_repos), current_owner: OwnerRecord = Depends(get_current_owner)):
    conn, repo, vehicle_repo, monitoring_repo = repos
    drivers = repo.get_all_drivers(owner_id=current_owner.owner_id)
    return [driver_to_dict(driver, vehicle_repo, monitoring_repo) for driver in drivers]


@router.get("/{driver_id}")
def get_driver(driver_id: int, repos=Depends(_get_repos), current_owner: OwnerRecord = Depends(get_current_owner)):
    conn, repo, vehicle_repo, monitoring_repo = repos
    driver = repo.get_driver_by_id(driver_id, owner_id=current_owner.owner_id)
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
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    conn, repo, vehicle_repo, monitoring_repo = repos
    updated = repo.update_driver_profile(
        driver_id=driver_id,
        name=profile.name,
        phone=profile.phone,
        email=profile.email,
        license_no=profile.license_no,
        owner_id=current_owner.owner_id,
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Driver not found",
        )

    driver = repo.get_driver_by_id(driver_id, owner_id=current_owner.owner_id)
    return driver_to_dict(driver, vehicle_repo, monitoring_repo)


@router.delete("/{driver_id}")
def delete_driver(driver_id: int, repos=Depends(_get_repos), current_owner: OwnerRecord = Depends(get_current_owner)):
    """
    Permanently fire and remove a driver from the fleet registry, cascading across
    active monitoring sessions and assignments while erasing biometrics and preserving audit logs.
    """
    conn, repo, vehicle_repo, monitoring_repo = repos
    deleted = repo.delete_driver(driver_id, owner_id=current_owner.owner_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Driver #{driver_id} not found",
        )
    return {"status": "success", "message": f"Driver #{driver_id} permanently removed"}