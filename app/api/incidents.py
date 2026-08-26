"""
Incident management REST endpoints.

GET  /incidents                            All incidents (fleet manager)
GET  /incidents/{incident_id}              Single incident details
GET  /incidents/{incident_id}/evidence     Serve evidence JPEG
GET  /incidents/driver/{driver_id}         Driver-specific incident history
GET  /incidents/session/{session_id}       Session-specific incident list
GET  /incidents/driver/{driver_id}/rating  Safety rating for a driver
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.database.connection import get_connection
from app.database.monitoring_repository import MonitoringRepository

router = APIRouter(prefix="/incidents", tags=["Incidents"])


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
        has_evidence=bool(inc.evidence_path and os.path.exists(
            os.path.join(str(settings.PROJECT_ROOT), inc.evidence_path)
        )),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[IncidentResponse])
def list_incidents(limit: int = 200, repo: MonitoringRepository = Depends(_get_repo)):
    """Return all incidents (most recent first). Limit defaults to 200."""
    return [_to_response(i) for i in repo.get_all_incidents(limit=limit)]


@router.get("/driver/{driver_id}/rating", response_model=SafetyRatingResponse)
def get_driver_rating(driver_id: int, repo: MonitoringRepository = Depends(_get_repo)):
    """Return the current safety rating for a driver."""
    rating = repo.get_safety_rating(driver_id)
    if not rating:
        # No sessions yet — return a fresh rating object
        from datetime import datetime, timezone
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
def get_driver_incidents(driver_id: int, repo: MonitoringRepository = Depends(_get_repo)):
    """Return all incidents for a specific driver."""
    return [_to_response(i) for i in repo.get_incidents_by_driver(driver_id)]


@router.get("/session/{session_id}", response_model=list[IncidentResponse])
def get_session_incidents(session_id: int, repo: MonitoringRepository = Depends(_get_repo)):
    """Return all incidents for a specific monitoring session."""
    return [_to_response(i) for i in repo.get_incidents_by_session(session_id)]


@router.get("/{incident_id}/evidence")
def get_evidence(incident_id: int, repo: MonitoringRepository = Depends(_get_repo)):
    """Serve the evidence screenshot JPEG for an incident."""
    incident = repo.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    if not incident.evidence_path:
        raise HTTPException(status_code=404, detail="No evidence captured for this incident")

    full_path = os.path.join(str(settings.PROJECT_ROOT), incident.evidence_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Evidence file not found on disk")

    return FileResponse(full_path, media_type="image/jpeg")


@router.delete("/{incident_id}/evidence")
def delete_evidence(incident_id: int, repo: MonitoringRepository = Depends(_get_repo)):
    """Delete the physical evidence screenshot file and remove evidence reference from SQLite."""
    deleted = repo.delete_incident_evidence(incident_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence for incident #{incident_id} not found",
        )
    return {"status": "success", "message": f"Evidence for incident #{incident_id} deleted"}


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: int, repo: MonitoringRepository = Depends(_get_repo)):
    """Return a single incident by ID."""
    incident = repo.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return _to_response(incident)

