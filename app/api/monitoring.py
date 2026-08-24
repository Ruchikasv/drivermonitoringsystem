"""
Session management REST endpoints.

POST   /sessions                  Create a new monitoring session
GET    /sessions/active           List all currently active sessions (owner portal)
GET    /sessions/{session_id}     Get session details + safety rating snapshot
DELETE /sessions/{session_id}     End a trip (COMPLETED)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database.connection import get_connection
from app.database.monitoring_repository import MonitoringRepository

router = APIRouter(prefix="/sessions", tags=["Monitoring Sessions"])


def _get_repo():
    conn = get_connection()
    try:
        yield MonitoringRepository(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    driver_id: int
    vehicle_id: Optional[int] = None


class SessionResponse(BaseModel):
    session_id: int
    driver_id: int
    vehicle_id: Optional[int]
    start_time: str
    end_time: Optional[str]
    status: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=SessionResponse, status_code=201)
def create_session(body: CreateSessionRequest, repo: MonitoringRepository = Depends(_get_repo)):
    """Create a new ACTIVE monitoring session for a driver."""
    session_id = repo.create_session(body.driver_id, body.vehicle_id)
    session = repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return SessionResponse(
        session_id=session.session_id,
        driver_id=session.driver_id,
        vehicle_id=session.vehicle_id,
        start_time=session.start_time,
        end_time=session.end_time,
        status=session.status,
    )


@router.get("/active", response_model=list[SessionResponse])
def list_active_sessions(repo: MonitoringRepository = Depends(_get_repo)):
    """Return all currently active monitoring sessions (for the owner portal)."""
    sessions = repo.get_active_sessions()
    return [
        SessionResponse(
            session_id=s.session_id,
            driver_id=s.driver_id,
            vehicle_id=s.vehicle_id,
            start_time=s.start_time,
            end_time=s.end_time,
            status=s.status,
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: int, repo: MonitoringRepository = Depends(_get_repo)):
    """Get a single monitoring session by ID."""
    session = repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return SessionResponse(
        session_id=session.session_id,
        driver_id=session.driver_id,
        vehicle_id=session.vehicle_id,
        start_time=session.start_time,
        end_time=session.end_time,
        status=session.status,
    )


@router.delete("/{session_id}", response_model=dict)
def end_session(session_id: int, repo: MonitoringRepository = Depends(_get_repo)):
    """End an active monitoring session (driver pressed END TRIP)."""
    session = repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session.status != "ACTIVE":
        raise HTTPException(status_code=400, detail=f"Session {session_id} is already {session.status}")

    repo.end_session(session_id, status="COMPLETED")

    # Recalculate safety rating immediately after session ends.
    repo.recalculate_safety_rating(session.driver_id)

    return {"message": f"Session {session_id} completed", "session_id": session_id}


@router.get("/live/all")
def get_all_live_sessions():
    """Return in-memory live metrics for all currently streaming sessions."""
    from app.api.monitoring_ws import get_all_live_metrics
    return get_all_live_metrics()


@router.get("/{session_id}/live")
def get_session_live_metrics(session_id: int):
    """Return in-memory live metrics for a specific active session."""
    from app.api.monitoring_ws import get_live_metrics
    data = get_live_metrics(session_id)
    if not data:
        return {"active": False, "session_id": session_id, "message": "No live stream active for this session"}
    return {"active": True, **data}
