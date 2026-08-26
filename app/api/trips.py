"""
Trips REST endpoint — maps monitoring sessions to trip records.

GET /trips   List all sessions as "trip" records for the frontend TripsPage.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
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
):
    """List all monitoring sessions as trip records with real incident metrics."""
    conn, m_repo, d_repo, v_repo = repos

    # Fetch all sessions (both active and completed)
    rows = conn.execute(
        "SELECT * FROM monitoring_sessions ORDER BY start_time DESC LIMIT 500"
    ).fetchall()

    trips = []
    for row in rows:
        from app.database.monitoring_repository import MonitoringSession
        session = MonitoringSession(**dict(row))

        # Apply filters
        if driver_id and session.driver_id != driver_id:
            continue
        if status and status != "ALL" and session.status != status:
            continue

        # Look up driver name
        driver = d_repo.get_driver_by_id(session.driver_id)
        driver_name = driver.name if driver else f"Driver #{session.driver_id}"

        # Look up vehicle registration
        vehicle_plate = "Unassigned"
        if session.vehicle_id:
            vehicle = v_repo.get_vehicle_by_id(session.vehicle_id)
            if vehicle:
                vehicle_plate = vehicle.registration_number

        # Calculate duration
        duration_minutes = None
        if session.end_time:
            try:
                start_dt = datetime.fromisoformat(session.start_time)
                end_dt = datetime.fromisoformat(session.end_time)
                duration_minutes = round((end_dt - start_dt).total_seconds() / 60.0, 1)
            except Exception:
                pass
        elif session.start_time:
            try:
                start_dt = datetime.fromisoformat(session.start_time)
                duration_minutes = round((datetime.utcnow() - start_dt).total_seconds() / 60.0, 1)
            except Exception:
                pass

        # Query session-specific incidents
        inc_stats = conn.execute(
            "SELECT COUNT(*) AS total_alerts, MAX(kss_score) AS peak_kss FROM monitoring_incidents WHERE session_id = ?",
            (session.session_id,),
        ).fetchone()

        alerts_count = inc_stats["total_alerts"] if inc_stats else 0
        peak_kss = inc_stats["peak_kss"] if inc_stats and inc_stats["peak_kss"] is not None else None
        max_drowsiness_score = f"KSS {peak_kss:.1f}" if peak_kss is not None else "KSS 1.0 (Safe)"

        # Map session status to trip status
        trip_status = "IN_PROGRESS" if session.status == "ACTIVE" else "COMPLETED"

        # Safety rating
        rating = m_repo.get_safety_rating(session.driver_id)
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
