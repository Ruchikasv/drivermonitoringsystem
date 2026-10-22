"""
REST endpoints for MQ-3 Alcohol Sensor Serial Telemetry & Prototype Lockout.

Endpoints:
  GET  /api/alcohol/status       - Live sensor readings, state machine phase, and lockout details
  POST /api/alcohol/acknowledge  - Prototype driver alarm acknowledgement (does not unlock trip)
  POST /api/alcohol/resolve      - Authorized fleet owner resolution with recorded audit reason
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_owner
from app.database.owner_repository import OwnerRecord
from app.hardware.alcohol_sensor import mq3_serial_reader

router = APIRouter(prefix="/api/alcohol", tags=["MQ-3 Serial Reader & Lockout"])


class AcknowledgeRequest(BaseModel):
    session_id: Optional[int] = None
    note: Optional[str] = "Driver alarm acknowledgement"


class ResolveRequest(BaseModel):
    reason: str = Field(..., min_length=3, description="Substantive reason for clearing safety lockout")
    incident_id: Optional[int] = None


from app.config import settings
from app.database.connection import get_connection_context

@router.get("/status")
def get_sensor_status() -> Dict[str, Any]:
    """
    Retrieve current MQ-3 serial connection status, state machine phase,
    latest analog/digital reading, reading timestamp, and active lockout details.
    """
    data = mq3_serial_reader.get_latest_reading()
    phone = getattr(settings, "OWNER_CONTACT_PHONE", "") or ""
    owner_name = None
    try:
        with get_connection_context() as conn:
            row = conn.execute("SELECT name FROM owners WHERE is_active = 1 ORDER BY owner_id ASC LIMIT 1").fetchone()
            if row:
                owner_name = row["name"] if hasattr(row, "__getitem__") else row[0]
    except Exception:
        pass

    data["owner_contact"] = {
        "name": owner_name or "Fleet Safety Manager",
        "phone": phone.strip() if phone and phone.strip() else None,
        "phone_configured": bool(phone and phone.strip()),
    }
    return data


@router.post("/acknowledge")
def acknowledge_alcohol_alarm(
    body: Optional[AcknowledgeRequest] = None,
) -> Dict[str, Any]:
    """
    Driver acknowledges the potential alcohol alarm.
    Silences the alarm. Does NOT unlock the trip or clear the lockout.
    """
    result = mq3_serial_reader.acknowledge_alarm()
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "No active lockout to acknowledge"),
        )
    return result


@router.post("/resolve")
def resolve_alcohol_lockout(
    body: ResolveRequest,
    current_owner: OwnerRecord = Depends(get_current_owner),
) -> Dict[str, Any]:
    """
    Authorized Fleet Owner resolves the potential-alcohol safety lockout.
    Records the resolution timestamp, owner ID, and resolution audit reason.
    """
    if not body.reason or len(body.reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A substantive reason must be provided to clear a safety lockout.",
        )

    result = mq3_serial_reader.resolve_lockout(
        owner_id=current_owner.owner_id,
        reason=body.reason.strip(),
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "No active lockout to resolve"),
        )

    return result
