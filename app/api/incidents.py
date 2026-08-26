"""
Incident management REST endpoints.

GET  /incidents                            All incidents (fleet manager)
GET  /incidents/{incident_id}              Single incident details
GET  /incidents/{incident_id}/evidence     Serve evidence JPEG
GET  /incidents/driver/{driver_id}         Driver-specific incident history
GET  /incidents/session/{session_id}       Session-specific incident list
GET  /incidents/driver/{driver_id}/rating  Safety rating for a driver
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.dependencies import get_current_owner
from app.config import settings
from app.database.connection import get_connection
from app.database.monitoring_repository import MonitoringRepository
from app.database.owner_repository import OwnerRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/incidents", tags=["Incidents"])


from app.database.driver_repository import DriverRepository


def _get_repos(conn=Depends(get_connection)):
    yield conn, MonitoringRepository(conn), DriverRepository(conn)


def _get_repo(conn=Depends(get_connection)):
    yield MonitoringRepository(conn)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class IncidentResponse(BaseModel):
    incident_id: int
    session_id: int
    driver_id: int
    vehicle_id: Optional[int]
    timestamp: str
    event_type: str
    alert_level: int
    kss_score: Optional[float]
    ear: Optional[float]
    mar: Optional[float]
    perclos: Optional[float]
    head_pitch_deg: Optional[float]
    evidence_path: Optional[str]
    has_evidence: bool


class SafetyRatingResponse(BaseModel):
    driver_id: int
    safety_score: Optional[float]
    total_sessions: int
    total_incidents: int
    critical_incidents: int
    last_updated: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(inc) -> IncidentResponse:
    full_path = os.path.join(str(settings.PROJECT_ROOT), inc.evidence_path) if inc.evidence_path else None
    file_exists = bool(full_path and os.path.exists(full_path))
    if inc.evidence_path and not file_exists:
        logger.warning(
            "[INCIDENTS] has_evidence=False for incident %s: evidence_path=%r resolved to %r which does not exist",
            inc.incident_id,
            inc.evidence_path,
            full_path,
        )
    elif inc.evidence_path and file_exists:
        logger.debug(
            "[INCIDENTS] has_evidence=True for incident %s: %r exists",
            inc.incident_id,
            full_path,
        )
    return IncidentResponse(
        incident_id=inc.incident_id,
        session_id=inc.session_id,
        driver_id=inc.driver_id,
        vehicle_id=inc.vehicle_id,
        timestamp=inc.timestamp,
        event_type=inc.event_type,
        alert_level=inc.alert_level,
        kss_score=inc.kss_score,
        ear=inc.ear,
        mar=inc.mar,
        perclos=inc.perclos,
        head_pitch_deg=inc.head_pitch_deg,
        evidence_path=inc.evidence_path,
        has_evidence=file_exists,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[IncidentResponse])
def list_incidents(
    limit: int = 200,
    repos=Depends(_get_repos),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    """Return all incidents for this owner (most recent first). Limit defaults to 200."""
    conn, repo, d_repo = repos
    return [_to_response(i) for i in repo.get_all_incidents(owner_id=current_owner.owner_id, limit=limit)]


@router.get("/driver/{driver_id}/rating", response_model=SafetyRatingResponse)
def get_driver_rating(
    driver_id: int,
    repos=Depends(_get_repos),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    """Return the current safety rating for a driver."""
    conn, repo, d_repo = repos
    driver = d_repo.get_driver_by_id(driver_id, owner_id=current_owner.owner_id)
    if driver is None:
        raise HTTPException(status_code=404, detail=f"Driver #{driver_id} not found")

    rating = repo.get_safety_rating(driver_id, owner_id=current_owner.owner_id)
    if not rating:
        rating = repo.recalculate_safety_rating(driver_id)
    return SafetyRatingResponse(
        driver_id=rating.driver_id,
        safety_score=rating.safety_score,
        total_sessions=rating.total_sessions,
        total_incidents=rating.total_incidents,
        critical_incidents=rating.critical_incidents,
        last_updated=rating.last_updated,
    )


@router.get("/driver/{driver_id}", response_model=list[IncidentResponse])
def get_driver_incidents(
    driver_id: int,
    repos=Depends(_get_repos),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    """Return all incidents for a specific driver belonging to current owner."""
    conn, repo, d_repo = repos
    driver = d_repo.get_driver_by_id(driver_id, owner_id=current_owner.owner_id)
    if driver is None:
        raise HTTPException(status_code=404, detail=f"Driver #{driver_id} not found")
    return [_to_response(i) for i in repo.get_incidents_by_driver(driver_id, owner_id=current_owner.owner_id)]


@router.get("/session/{session_id}", response_model=list[IncidentResponse])
def get_session_incidents(
    session_id: int,
    repos=Depends(_get_repos),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    """Return all incidents for a specific monitoring session belonging to current owner."""
    conn, repo, d_repo = repos
    session = repo.get_session(session_id, owner_id=current_owner.owner_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session #{session_id} not found")
    return [_to_response(i) for i in repo.get_incidents_by_session(session_id, owner_id=current_owner.owner_id)]


@router.get("/{incident_id}/evidence")
def get_evidence(
    incident_id: int,
    repos=Depends(_get_repos),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    """Serve the evidence screenshot JPEG for an incident, validating owner access."""
    conn, repo, d_repo = repos
    incident = repo.get_incident(incident_id, owner_id=current_owner.owner_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    if not incident.evidence_path:
        raise HTTPException(status_code=404, detail="No evidence captured for this incident")

    full_path = os.path.join(str(settings.PROJECT_ROOT), incident.evidence_path)
    logger.info(
        "[EVIDENCE API] Serving evidence for incident %s: rel=%r full=%r exists=%s",
        incident_id,
        incident.evidence_path,
        full_path,
        os.path.exists(full_path),
    )
    if not os.path.exists(full_path):
        logger.error(
            "[EVIDENCE API] File NOT found on disk for incident %s: %r",
            incident_id,
            full_path,
        )
        raise HTTPException(status_code=404, detail="Evidence file not found on disk")

    return FileResponse(full_path, media_type="image/jpeg")


@router.delete("/{incident_id}/evidence")
def delete_evidence(
    incident_id: int,
    repos=Depends(_get_repos),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    """Delete the physical evidence screenshot file and remove evidence reference from the database."""
    conn, repo, d_repo = repos
    deleted = repo.delete_incident_evidence(incident_id, owner_id=current_owner.owner_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence for incident #{incident_id} not found or unauthorized",
        )
    return {"status": "success", "message": f"Evidence for incident #{incident_id} deleted"}


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: int,
    repos=Depends(_get_repos),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    """Return a single incident by ID with owner access verification."""
    conn, repo, d_repo = repos
    incident = repo.get_incident(incident_id, owner_id=current_owner.owner_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return _to_response(incident)


