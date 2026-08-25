"""
Alerts REST endpoint — serves persisted monitoring incidents as frontend alerts.

GET /alerts   List all incidents formatted for the frontend alertService.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.vehicle_repository import VehicleRepository

router = APIRouter(prefix="/alerts", tags=["Alerts"])


class AlertResponse(BaseModel):
    alert_id: str
    incident_id: int
    driver_id: int
    driver_name: str
    level: int
    event_type: str
    timestamp: str
    vehicle_plate: str
    location: str
    notes: str


def _get_repos(conn=Depends(get_connection)):
    yield conn, MonitoringRepository(conn), DriverRepository(conn), VehicleRepository(conn)


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    driver_id: Optional[int] = Query(None),
    level: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    repos=Depends(_get_repos),
):
    """List all monitoring incidents as alert records for the frontend."""
    conn, m_repo, d_repo, v_repo = repos

    # Get incidents
    if driver_id and driver_id != "ALL":
        incidents = m_repo.get_incidents_by_driver(int(driver_id))
    else:
        incidents = m_repo.get_all_incidents(limit=200)

    alerts = []
    # Cache driver/vehicle lookups
    driver_cache = {}
    vehicle_cache = {}

    for inc in incidents:
        # Apply level filter
        if level and level != "ALL" and inc.alert_level != int(level):
            continue

        # Lookup driver name (cached)
        if inc.driver_id not in driver_cache:
            driver = d_repo.get_driver_by_id(inc.driver_id)
            driver_cache[inc.driver_id] = driver.name if driver else f"Driver #{inc.driver_id}"
        driver_name = driver_cache[inc.driver_id]

        # Lookup vehicle plate (cached)
        vehicle_plate = "Unassigned"
        if inc.vehicle_id:
            if inc.vehicle_id not in vehicle_cache:
                vehicle = v_repo.get_vehicle_by_id(inc.vehicle_id)
                vehicle_cache[inc.vehicle_id] = vehicle.registration_number if vehicle else "Unknown"
            vehicle_plate = vehicle_cache[inc.vehicle_id]

        # Build human-readable notes from metrics
        notes_parts = []
        if inc.ear is not None:
            notes_parts.append(f"EAR={inc.ear:.3f}")
        if inc.kss_score is not None:
            notes_parts.append(f"KSS={inc.kss_score:.1f}")
        if inc.perclos is not None:
            notes_parts.append(f"PERCLOS={inc.perclos*100:.1f}%")
        notes = ", ".join(notes_parts) if notes_parts else "Drowsiness event"

        alert = AlertResponse(
            alert_id=f"ALT-{inc.incident_id:04d}",
            incident_id=inc.incident_id,
            driver_id=inc.driver_id,
            driver_name=driver_name,
            level=inc.alert_level,
            event_type=inc.event_type.capitalize(),
            timestamp=inc.timestamp,
            vehicle_plate=vehicle_plate,
            location="GPS N/A (laptop mode)",
            notes=notes,
        )

        # Apply search filter
        if search:
            query = search.lower()
            searchable = f"{alert.driver_name} {alert.event_type} {alert.vehicle_plate}".lower()
            if query not in searchable:
                continue

        alerts.append(alert)

    return alerts
