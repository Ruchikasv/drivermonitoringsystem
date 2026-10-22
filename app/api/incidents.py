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

from fastapi import APIRouter, Depends, HTTPException, Query
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
    distraction_type: Optional[str] = None
    duration_seconds: Optional[float] = None
    raw_evidence_path: Optional[str] = None
    has_raw_evidence: bool = False
    warning_evidence_path: Optional[str] = None
    has_warning_evidence: bool = False
    evidence_status: str = "NO_EVIDENCE"  # "AVAILABLE", "NOT_CAPTURED", "REMOVED"


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
    primary_rel = inc.evidence_path
    full_path = os.path.join(str(settings.PROJECT_ROOT), primary_rel) if primary_rel else None
    file_exists = bool(full_path and os.path.exists(full_path))

    raw_evidence_path: Optional[str] = None
    has_raw_evidence: bool = False
    warning_evidence_path: Optional[str] = None
    has_warning_evidence: bool = False

    if not primary_rel:
        evidence_status = "NOT_CAPTURED"
    elif not file_exists:
        evidence_status = "REMOVED"
        logger.warning(
            "[INCIDENTS] Evidence file removed/missing for incident %s: path=%r",
            inc.incident_id,
            primary_rel,
        )
    else:
        evidence_status = "AVAILABLE"
        if "_alcohol_warning.jpg" in primary_rel:
            warning_evidence_path = primary_rel
            has_warning_evidence = True
            raw_rel = primary_rel.replace("_alcohol_warning.jpg", "_alcohol_raw.jpg")
            if os.path.exists(os.path.join(str(settings.PROJECT_ROOT), raw_rel)):
                raw_evidence_path = raw_rel
                has_raw_evidence = True
        elif "_alcohol_raw.jpg" in primary_rel:
            raw_evidence_path = primary_rel
            has_raw_evidence = True
            warn_rel = primary_rel.replace("_alcohol_raw.jpg", "_alcohol_warning.jpg")
            if os.path.exists(os.path.join(str(settings.PROJECT_ROOT), warn_rel)):
                warning_evidence_path = warn_rel
                has_warning_evidence = True
        else:
            warning_evidence_path = primary_rel
            has_warning_evidence = True

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
        distraction_type=getattr(inc, "distraction_type", None),
        duration_seconds=getattr(inc, "duration_seconds", None),
        raw_evidence_path=raw_evidence_path,
        has_raw_evidence=has_raw_evidence,
        warning_evidence_path=warning_evidence_path,
        has_warning_evidence=has_warning_evidence,
        evidence_status=evidence_status,
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
    type: str = Query("primary", description="'primary', 'warning', or 'raw'"),
    repos=Depends(_get_repos),
    current_owner: OwnerRecord = Depends(get_current_owner),
):
    """Serve the evidence screenshot JPEG for an incident, validating owner access and supporting raw vs warning views."""
    conn, repo, d_repo = repos
    incident = repo.get_incident(incident_id, owner_id=current_owner.owner_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    if not incident.evidence_path:
        raise HTTPException(status_code=404, detail="No evidence captured for this incident")

    target_rel = incident.evidence_path
    if type == "raw":
        if "_alcohol_warning.jpg" in incident.evidence_path:
            target_rel = incident.evidence_path.replace("_alcohol_warning.jpg", "_alcohol_raw.jpg")
        elif "_alcohol_raw.jpg" in incident.evidence_path:
            target_rel = incident.evidence_path
        else:
            raise HTTPException(status_code=404, detail="Raw driver frame not captured separately for this incident")
    elif type == "warning":
        if "_alcohol_raw.jpg" in incident.evidence_path:
            target_rel = incident.evidence_path.replace("_alcohol_raw.jpg", "_alcohol_warning.jpg")
        else:
            target_rel = incident.evidence_path

    full_path = os.path.join(str(settings.PROJECT_ROOT), target_rel)
    logger.info(
        "[EVIDENCE API] Serving evidence for incident %s (type=%s): rel=%r full=%r exists=%s",
        incident_id,
        type,
        target_rel,
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


