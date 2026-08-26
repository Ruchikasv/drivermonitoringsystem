"""
Trips REST endpoint — maps monitoring sessions to trip records.

GET /trips   List all sessions as "trip" records for the frontend TripsPage.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.dependencies import get_current_owner
from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.owner_repository import OwnerRecord
from app.database.vehicle_repository import VehicleRepository

router = APIRouter(prefix="/trips", tags=["Trips"])


class TripResponse(BaseModel):
    trip_id: str
    session_id: int
    driver_id: int
    driver_name: str
    vehicle_plate: str
    origin: str
    destination: str
    start_time: str
    end_time: Optional[str]
    status: str
    duration_minutes: Optional[float]
    total_paused_minutes: Optional[float] = 0.0
    active_duration_minutes: Optional[float] = 0.0
    safety_score: Optional[float]
    alerts_count: int = 0
    max_drowsiness_score: str = "KSS 1.0"
    alcohol_status: str = "Normal"


def _get_repos(conn=Depends(get_connection)):
    yield conn, MonitoringRepository(conn), DriverRepository(conn), VehicleRepository(conn)


@router.get("", response_model=list[TripResponse])
def list_trips(
    driver_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    repos=Depends(_get_repos),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    """List all monitoring sessions as trip records with real incident metrics strictly for current owner."""
    conn, m_repo, d_repo, v_repo = repos

    # If driver_id is provided, verify driver belongs to this owner
    if driver_id:
        driver_check = d_repo.get_driver_by_id(driver_id, owner_id=current_owner.owner_id)
        if driver_check is None:
            return []

    # Fetch all sessions strictly for this owner
    rows = conn.execute(
        """
        SELECT * FROM monitoring_sessions
        WHERE owner_id = ?
        ORDER BY start_time DESC LIMIT 500
        """,
        (current_owner.owner_id,),
    ).fetchall()

    trips = []
    for row in rows:
        from datetime import datetime, timezone
        from app.database.monitoring_repository import MonitoringSession
        session = MonitoringSession(**dict(row))

        # Map session status to trip status
        if session.status == "ACTIVE":
            trip_status = "RUNNING"
        elif session.status == "PAUSED":
            trip_status = "PAUSED"
        else:
            trip_status = "COMPLETED"

        # Apply filters
        if driver_id and session.driver_id != driver_id:
            continue
        if status and status != "ALL":
            if status in ("RUNNING", "IN_PROGRESS") and session.status != "ACTIVE":
                continue
            elif status == "PAUSED" and session.status != "PAUSED":
                continue
            elif status == "COMPLETED" and session.status not in ("COMPLETED", "INTERRUPTED"):
                continue

        # Look up driver name
        driver = d_repo.get_driver_by_id(session.driver_id, owner_id=current_owner.owner_id)
        driver_name = driver.name if driver else f"Driver #{session.driver_id}"

        # Look up vehicle registration
        vehicle_plate = "Unassigned"
        if session.vehicle_id:
            vehicle = v_repo.get_vehicle_by_id(session.vehicle_id, owner_id=current_owner.owner_id)
            if vehicle:
                vehicle_plate = vehicle.registration_number

        # Calculate paused and total duration
        total_paused_seconds = float(session.total_paused_seconds or 0.0)
        if session.status == "PAUSED" and session.pause_started_at:
            try:
                p_start = datetime.fromisoformat(session.pause_started_at)
                if p_start.tzinfo is None:
                    p_start = p_start.replace(tzinfo=timezone.utc)
                total_paused_seconds += max(0.0, (datetime.now(timezone.utc) - p_start).total_seconds())
            except Exception:
                pass

        total_paused_minutes = round(total_paused_seconds / 60.0, 1)

        duration_minutes = None
        active_duration_minutes = None
        if session.end_time:
            try:
                start_dt = datetime.fromisoformat(session.start_time)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                end_dt = datetime.fromisoformat(session.end_time)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                duration_minutes = round((end_dt - start_dt).total_seconds() / 60.0, 1)
                active_duration_minutes = max(0.0, round(duration_minutes - total_paused_minutes, 1))
            except Exception:
                pass
        elif session.start_time:
            try:
                start_dt = datetime.fromisoformat(session.start_time)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                duration_minutes = round((datetime.now(timezone.utc) - start_dt).total_seconds() / 60.0, 1)
                active_duration_minutes = max(0.0, round(duration_minutes - total_paused_minutes, 1))
            except Exception:
                pass

        # Query session-specific incidents strictly for this owner
        inc_stats = conn.execute(
            "SELECT COUNT(*) AS total_alerts, MAX(kss_score) AS peak_kss FROM monitoring_incidents WHERE session_id = ? AND owner_id = ?",
            (session.session_id, current_owner.owner_id),
        ).fetchone()

        alerts_count = inc_stats["total_alerts"] if inc_stats else 0
        peak_kss = inc_stats["peak_kss"] if inc_stats and inc_stats["peak_kss"] is not None else None
        max_drowsiness_score = f"KSS {peak_kss:.1f}" if peak_kss is not None else "KSS 1.0 (Safe)"

        # Safety rating
        rating = m_repo.get_safety_rating(session.driver_id, owner_id=current_owner.owner_id)
        safety_score = rating.safety_score if rating else None

        trip = TripResponse(
            trip_id=f"TRIP-{session.session_id:04d}",
            session_id=session.session_id,
            driver_id=session.driver_id,
            driver_name=driver_name,
            vehicle_plate=vehicle_plate,
            origin="Depot / Fleet Terminal",
            destination="Commercial Route (Prototype)",
            start_time=session.start_time,
            end_time=session.end_time,
            status=trip_status,
            duration_minutes=duration_minutes,
            total_paused_minutes=total_paused_minutes,
            active_duration_minutes=active_duration_minutes,
            safety_score=safety_score,
            alerts_count=alerts_count,
            max_drowsiness_score=max_drowsiness_score,
            alcohol_status="Pass (0.00% BAC • Standby)",
        )

        # Apply search filter
        if search:
            query = search.lower()
            searchable = f"{trip.trip_id} {trip.driver_name} {trip.vehicle_plate}".lower()
            if query not in searchable:
                continue

        trips.append(trip)

    return trips
