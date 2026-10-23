"""
Session management REST endpoints.

POST   /sessions                  Create a new monitoring session
GET    /sessions/active           List all currently active sessions (owner portal)
GET    /sessions/{session_id}     Get session details + safety rating snapshot
DELETE /sessions/{session_id}     End a trip (COMPLETED)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.dependencies import get_optional_owner
from app.database.connection import get_connection
from app.database.monitoring_repository import MonitoringRepository, MonitoringSession
from app.database.owner_repository import OwnerRecord

router = APIRouter(prefix="/sessions", tags=["Monitoring Sessions"])


def _get_repo(conn=Depends(get_connection)):
    yield MonitoringRepository(conn)


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
    session_token: Optional[str] = None
    pause_started_at: Optional[str] = None
    total_paused_seconds: float = 0.0
    is_paused: bool = False
    is_locked: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=SessionResponse, status_code=201)
def create_session(
    body: CreateSessionRequest,
    repo: MonitoringRepository = Depends(_get_repo),
    current_owner: Optional[OwnerRecord] = Depends(get_optional_owner),
):
    """Create a new ACTIVE monitoring session for a driver, strictly blocked if locked out."""
    from app.hardware.alcohol_sensor import mq3_serial_reader
    if mq3_serial_reader.is_locked():
        raise HTTPException(
            status_code=423,
            detail="VEHICLE OPERATION LOCKED OUT: Potential alcohol detected. Trip start is restricted pending authorized owner resolution.",
        )

    owner_id = current_owner.owner_id if current_owner else None
    session_id = repo.create_session(body.driver_id, body.vehicle_id, owner_id=owner_id)
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
        session_token=session.session_token,
        pause_started_at=session.pause_started_at,
        total_paused_seconds=session.total_paused_seconds,
        is_paused=(session.status == "PAUSED"),
        is_locked=mq3_serial_reader.is_locked(),
    )


@router.get("/active", response_model=list[SessionResponse])
def list_active_sessions(
    repo: MonitoringRepository = Depends(_get_repo),
    current_owner: Optional[OwnerRecord] = Depends(get_optional_owner),
):
    """Return all currently active and paused monitoring sessions (scoped to owner if authenticated)."""
    from app.hardware.alcohol_sensor import mq3_serial_reader
    is_locked = mq3_serial_reader.is_locked()
    owner_id = current_owner.owner_id if current_owner else None
    sessions = repo.get_active_sessions(owner_id=owner_id, include_paused=True)
    return [
        SessionResponse(
            session_id=s.session_id,
            driver_id=s.driver_id,
            vehicle_id=s.vehicle_id,
            start_time=s.start_time,
            end_time=s.end_time,
            status="PAUSED" if is_locked else s.status,
            session_token=s.session_token,
            pause_started_at=s.pause_started_at,
            total_paused_seconds=s.total_paused_seconds,
            is_paused=True if is_locked else (s.status == "PAUSED"),
            is_locked=is_locked,
        )
        for s in sessions
    ]


def _get_authorized_session(
    session_id: int,
    token: Optional[str],
    current_owner: Optional[OwnerRecord],
    repo: MonitoringRepository,
) -> MonitoringSession:
    """Authorize access to a session via driver capability token or owner account."""
    session = repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # 1. If driver capability token is provided, authorize via token
    if token:
        if not session.session_token or session.session_token.strip() != token.strip():
            raise HTTPException(status_code=403, detail="Invalid session token for this monitoring session")
        return session

    # 2. If accessed by an owner without token, ensure tenant scoping
    if current_owner is not None and session.owner_id is not None:
        if session.owner_id != current_owner.owner_id:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return session


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: int,
    token: Optional[str] = Query(None, description="Driver session token"),
    repo: MonitoringRepository = Depends(_get_repo),
    current_owner: Optional[OwnerRecord] = Depends(get_optional_owner),
):
    """Get a single monitoring session by ID with owner or driver-token validation."""
    from app.hardware.alcohol_sensor import mq3_serial_reader
    is_locked = mq3_serial_reader.is_locked()
    session = _get_authorized_session(session_id, token, current_owner, repo)
    return SessionResponse(
        session_id=session.session_id,
        driver_id=session.driver_id,
        vehicle_id=session.vehicle_id,
        start_time=session.start_time,
        end_time=session.end_time,
        status="PAUSED" if is_locked else session.status,
        session_token=session.session_token,
        pause_started_at=session.pause_started_at,
        total_paused_seconds=session.total_paused_seconds,
        is_paused=True if is_locked else (session.status == "PAUSED"),
        is_locked=is_locked,
    )


@router.post("/{session_id}/pause", response_model=SessionResponse)
def pause_session(
    session_id: int,
    token: Optional[str] = Query(None, description="Driver session token"),
    repo: MonitoringRepository = Depends(_get_repo),
    current_owner: Optional[OwnerRecord] = Depends(get_optional_owner),
):
    """Pause an active monitoring session."""
    session = _get_authorized_session(session_id, token, current_owner, repo)
    if session.status == "PAUSED":
        raise HTTPException(status_code=400, detail="Trip is already paused")
    if session.status != "ACTIVE":
        raise HTTPException(status_code=400, detail=f"Cannot pause trip in status '{session.status}'")

    success = repo.pause_session(session_id, owner_id=None)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to pause session")

    # Update in-memory live metrics cache to PAUSED
    from app.api.monitoring_ws import update_live_session_pause_state
    update_live_session_pause_state(session_id, is_paused=True)

    updated_session = repo.get_session(session_id)
    return SessionResponse(
        session_id=updated_session.session_id,
        driver_id=updated_session.driver_id,
        vehicle_id=updated_session.vehicle_id,
        start_time=updated_session.start_time,
        end_time=updated_session.end_time,
        status=updated_session.status,
        session_token=updated_session.session_token,
        pause_started_at=updated_session.pause_started_at,
        total_paused_seconds=updated_session.total_paused_seconds,
        is_paused=True,
    )


@router.post("/{session_id}/resume", response_model=SessionResponse)
def resume_session(
    session_id: int,
    token: Optional[str] = Query(None, description="Driver session token"),
    repo: MonitoringRepository = Depends(_get_repo),
    current_owner: Optional[OwnerRecord] = Depends(get_optional_owner),
):
    """Resume a paused monitoring session, strictly blocked if locked out."""
    from app.hardware.alcohol_sensor import mq3_serial_reader
    if mq3_serial_reader.is_locked():
        raise HTTPException(
            status_code=423,
            detail="VEHICLE OPERATION LOCKED OUT: Potential alcohol detected. Trip resume is restricted pending authorized owner resolution.",
        )

    session = _get_authorized_session(session_id, token, current_owner, repo)
    if session.status == "ACTIVE":
        raise HTTPException(status_code=400, detail="Trip is already running")
    if session.status != "PAUSED":
        raise HTTPException(status_code=400, detail=f"Cannot resume trip in status '{session.status}'")

    success = repo.resume_session(session_id, owner_id=None)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to resume session")

    # Update in-memory live metrics cache to ACTIVE
    from app.api.monitoring_ws import update_live_session_pause_state
    update_live_session_pause_state(session_id, is_paused=False)

    updated_session = repo.get_session(session_id)
    return SessionResponse(
        session_id=updated_session.session_id,
        driver_id=updated_session.driver_id,
        vehicle_id=updated_session.vehicle_id,
        start_time=updated_session.start_time,
        end_time=updated_session.end_time,
        status=updated_session.status,
        session_token=updated_session.session_token,
        pause_started_at=updated_session.pause_started_at,
        total_paused_seconds=updated_session.total_paused_seconds,
        is_paused=False,
    )


@router.delete("/{session_id}", response_model=dict)
def end_session(
    session_id: int,
    token: Optional[str] = Query(None, description="Driver session token"),
    repo: MonitoringRepository = Depends(_get_repo),
    current_owner: Optional[OwnerRecord] = Depends(get_optional_owner),
):
    """End a monitoring session (driver pressed END TRIP or owner ended)."""
    session = _get_authorized_session(session_id, token, current_owner, repo)
    if session.status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(status_code=400, detail=f"Session {session_id} is already {session.status}")

    repo.end_session(session_id, status="COMPLETED")

    # Recalculate safety rating immediately after session ends.
    repo.recalculate_safety_rating(session.driver_id)

    return {"message": f"Session {session_id} completed", "session_id": session_id}


@router.get("/live/all")
def get_all_live_sessions(current_owner: Optional[OwnerRecord] = Depends(get_optional_owner)):
    """Return in-memory live metrics for all currently streaming sessions (filtered by owner)."""
    from app.api.monitoring_ws import get_all_live_metrics
    owner_id = current_owner.owner_id if current_owner else None
    return get_all_live_metrics(owner_id=owner_id)


@router.get("/{session_id}/live")
def get_session_live_metrics(
    session_id: int,
    current_owner: Optional[OwnerRecord] = Depends(get_optional_owner),
):
    """Return in-memory live metrics for a specific active session with owner check."""
    from app.api.monitoring_ws import get_live_metrics
    data = get_live_metrics(session_id)
    if not data:
        return {"active": False, "session_id": session_id, "message": "No live stream active for this session"}
    if current_owner and data.get("owner_id") is not None and data.get("owner_id") != current_owner.owner_id:
        raise HTTPException(status_code=404, detail="No live stream active for this session")
    return {"active": True, **data}
