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
import logging
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.face_recognition.comparator import find_best_match, average_embeddings, cosine_similarity
from app.face_recognition.detector import FaceDetector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

def _get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()

# Shared detector singleton and lifecycle state
_detector: Optional[FaceDetector] = None
_model_ready: bool = False
_model_error: Optional[str] = None


def warmup_detector() -> bool:
    """Preload InsightFace model on server startup."""
    global _detector, _model_ready, _model_error
    logger.info("[AUTH MODEL] Initializing InsightFace...")
    try:
        if _detector is None:
            _detector = FaceDetector()
        _detector._ensure_model_loaded()
        _model_ready = True
        _model_error = None
        logger.info("[AUTH MODEL] InsightFace ready")
        logger.info("[AUTH MODEL] Registration service ready")
        return True
    except Exception as exc:
        _model_ready = False
        _model_error = str(exc)
        logger.error("[AUTH MODEL] InsightFace initialization failed: %s", exc)
        return False


def is_model_ready() -> tuple[bool, Optional[str]]:
    """Return whether the face recognition model is initialized and ready."""
    return _model_ready, _model_error


def _get_detector() -> FaceDetector:
    global _detector, _model_ready, _model_error
    if not _model_ready or _detector is None:
        # Attempt initialization if not ready
        success = warmup_detector()
        if not success or _detector is None:
            raise HTTPException(
                status_code=503,
                detail=f"Face recognition service is unavailable: {_model_error or 'Model initialization failed'}",
            )
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
    logger.info("[AUTH REGISTER] request received")
    
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Driver name is required")
    if not body.frames_b64:
        raise HTTPException(status_code=400, detail="At least one frame is required")

    logger.info("[AUTH REGISTER] face samples received: %d frames", len(body.frames_b64))

    repo = DriverRepository(conn)

    # 1. Check duplicate license number if provided
    if body.license_no and body.license_no.strip():
        lic = body.license_no.strip()
        existing_by_lic = conn.execute(
            "SELECT * FROM drivers WHERE LOWER(license_no) = LOWER(?)",
            (lic,)
        ).fetchone()
        if existing_by_lic:
            logger.warning("[AUTH REGISTER] duplicate license_no '%s' matches driver_id %s", lic, existing_by_lic["driver_id"])
            raise HTTPException(
                status_code=409,
                detail=f"Driving license '{lic}' is already registered to driver '{existing_by_lic['name']}' (ID #{existing_by_lic['driver_id']}).",
            )

    # 2. Ensure model is loaded and ready
    detector = _get_detector()
    logger.info("[AUTH REGISTER] face model ready")

    # 3. Process frames and extract embeddings
    embeddings = []
    for idx, b64 in enumerate(body.frames_b64):
        try:
            frame = _decode_frame(b64)
            face = detector.detect_single_face(frame)
            if face is not None:
                embeddings.append(face.embedding)
        except HTTPException:
            raise
        except Exception as err:
            logger.warning("[AUTH REGISTER] error extracting face from frame %d: %s", idx, err)
            continue

    if not embeddings:
        logger.warning("[AUTH REGISTER] no face detected in any of the %d provided frames", len(body.frames_b64))
        raise HTTPException(
            status_code=422,
            detail="No face detected in any of the provided frames. "
                   "Please ensure the driver is facing the camera with good lighting.",
        )

    # 4. Average embeddings and normalize
    avg_emb = average_embeddings(embeddings)
    logger.info("[AUTH REGISTER] face embedding generated")

    # 5. Check duplicate face biometrics against all registered drivers
    all_drivers = repo.get_all_drivers()
    for existing in all_drivers:
        sim = cosine_similarity(avg_emb, existing.face_embedding)
        if sim >= settings.DUPLICATE_DETECTION_THRESHOLD:
            logger.warning(
                "[AUTH REGISTER] duplicate biometrics detected: matches driver '%s' (ID %d) with similarity %.3f",
                existing.name, existing.driver_id, sim
            )
            raise HTTPException(
                status_code=409,
                detail=f"Driver '{existing.name}' (ID #{existing.driver_id}) is already registered with matching facial biometrics (similarity: {sim:.2f}).",
            )

    # 6. Database insert
    logger.info("[AUTH REGISTER] database insert started")
    driver_id = repo.add_driver(
        name=body.name.strip(),
        embedding=avg_emb,
        phone=body.phone.strip() if body.phone else None,
        email=body.email.strip() if body.email else None,
        license_no=body.license_no.strip() if body.license_no else None,
    )
    logger.info("[AUTH REGISTER] database insert completed")

    resp = RegisterResponse(
        driver_id=driver_id,
        name=body.name.strip(),
        message=f"Driver '{body.name.strip()}' registered successfully (ID #{driver_id}). "
                f"Used {len(embeddings)}/{len(body.frames_b64)} biometric frames.",
    )
    logger.info("[AUTH REGISTER] response returned")
    return resp


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

