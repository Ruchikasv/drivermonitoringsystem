"""
Driver facial authentication REST endpoints.

POST /auth/register       Register a new driver via ArcFace face embedding
POST /auth/authenticate   Authenticate a driver by face match

Both endpoints accept base64-encoded JPEG frames captured by the browser's
MediaDevices API (getUserMedia → canvas.toDataURL → send to backend).

The ArcFace pipeline is shared with the existing scripts/register_driver.py
and scripts/authenticate_driver.py CLI tools; these endpoints wrap the same
FaceDetector + DriverRepository logic.
"""

import base64
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.face_recognition.comparator import find_best_match
from app.face_recognition.detector import FaceDetector

router = APIRouter(prefix="/auth", tags=["Authentication"])

def _get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()

# Lazy-loaded detector shared across requests (ArcFace init is slow).
_detector: Optional[FaceDetector] = None



def _get_detector() -> FaceDetector:
    global _detector
    if _detector is None:
        _detector = FaceDetector()
    return _detector


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _decode_frame(b64_data: str) -> np.ndarray:
    """Decode a base64 JPEG string (optionally prefixed with a data-URI header)
    into a BGR numpy array."""
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]
    raw_bytes = base64.b64decode(b64_data)
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image data — could not decode JPEG")
    return frame


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    name: str
    frames_b64: list[str]              # 5–15 base64 JPEG frames
    phone: Optional[str] = None
    email: Optional[str] = None
    license_no: Optional[str] = None


class RegisterResponse(BaseModel):
    driver_id: int
    name: str
    message: str


class AuthenticateRequest(BaseModel):
    frame_b64: str                     # single base64 JPEG frame


class AuthenticateResponse(BaseModel):
    driver_id: int
    name: str
    similarity: float
    vehicle_id: Optional[int]
    vehicle_registration: Optional[str]
    vehicle_model: Optional[str]
    vehicle_type: Optional[str]
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=RegisterResponse, status_code=201)
def register_driver(body: RegisterRequest, conn=Depends(_get_db)):
    """
    Register a new driver.

    Accepts 5–15 base64 JPEG frames from the browser camera, extracts an
    ArcFace embedding from each, averages them, and stores the result.
    """
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Driver name is required")
    if not body.frames_b64:
        raise HTTPException(status_code=400, detail="At least one frame is required")

    detector = _get_detector()
    embeddings = []

    for idx, b64 in enumerate(body.frames_b64):
        frame = _decode_frame(b64)
        face = detector.detect_single_face(frame)
        if face is None:
            continue  # Skip frames with no face detected
        embeddings.append(face.embedding)

    if not embeddings:
        raise HTTPException(
            status_code=422,
            detail="No face detected in any of the provided frames. "
                   "Please ensure the driver is facing the camera with good lighting.",
        )

    # Average the embeddings (ArcFace vectors are unit-normalised, so the
    # average is then re-normalised to stay on the unit sphere).
    from app.face_recognition.comparator import average_embeddings
    avg_emb = average_embeddings(embeddings)

    repo = DriverRepository(conn)
    driver_id = repo.add_driver(
        name=body.name.strip(),
        embedding=avg_emb,
        phone=body.phone,
        email=body.email,
        license_no=body.license_no,
    )

    return RegisterResponse(
        driver_id=driver_id,
        name=body.name.strip(),
        message=f"Driver '{body.name.strip()}' registered successfully (ID {driver_id}). "
                f"Used {len(embeddings)}/{len(body.frames_b64)} frames.",
    )


@router.post("/authenticate", response_model=AuthenticateResponse)
def authenticate_driver(body: AuthenticateRequest, conn=Depends(_get_db)):
    """
    Authenticate a driver from a single captured frame.

    Extracts an ArcFace embedding from the frame and compares it against all
    stored drivers.  Returns the best match above threshold with the driver's
    current vehicle assignment.
    """
    frame = _decode_frame(body.frame_b64)
    detector = _get_detector()
    face = detector.detect_single_face(frame)
    emb = face.embedding if face is not None else None

    if emb is None:
        raise HTTPException(
            status_code=422,
            detail="No face detected in the provided frame. "
                   "Please ensure the driver is facing the camera with good lighting.",
        )

    repo = DriverRepository(conn)
    all_drivers = repo.get_all_drivers()

    if not all_drivers:
        raise HTTPException(status_code=404, detail="No drivers registered in the system")

    auth_result = find_best_match(emb, all_drivers)

    if not auth_result.is_match:
        raise HTTPException(
            status_code=401,
            detail="Face not recognised. Please ensure your face is fully visible "
                   "or register first.",
        )

    driver_id = auth_result.driver_id
    name = auth_result.driver_name
    similarity = auth_result.similarity

    # Fetch the driver's current vehicle assignment
    from app.database.vehicle_repository import VehicleRepository
    v_repo = VehicleRepository(conn)
    assignment = v_repo.get_current_assignment(driver_id)

    vehicle_id = None
    vehicle_registration = None
    vehicle_model = None
    vehicle_type = None

    if assignment:
        vehicle = v_repo.get_vehicle_by_id(assignment.vehicle_id)
        if vehicle:
            vehicle_id = vehicle.vehicle_id
            vehicle_registration = vehicle.registration_number
            vehicle_model = vehicle.model
            vehicle_type = vehicle.vehicle_type

    return AuthenticateResponse(
        driver_id=driver_id,
        name=name,
        similarity=round(float(similarity), 4),
        vehicle_id=vehicle_id,
        vehicle_registration=vehicle_registration,
        vehicle_model=vehicle_model,
        vehicle_type=vehicle_type,
        message=(
            f"Welcome, {name}! Vehicle: {vehicle_registration or 'Not assigned'}"
        ),
    )

