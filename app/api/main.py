"""
FastAPI application entry point for the Fleet Safety Management System.

Phase 1  — Driver information, profile, vehicle assignment
Phase 2  — Drowsiness detection engine (NeuraDrive / FYP integration)
Phase 3+ — Monitoring sessions, incidents, evidence, WebSocket streaming
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.drivers import router as drivers_router
from app.api.vehicles import router as vehicles_router
from app.api import auth as auth_module
from app.api.auth import router as auth_router
from app.api.owner_auth import router as owner_auth_router
from app.api.monitoring import router as monitoring_router
from app.api.incidents import router as incidents_router
from app.api.monitoring_ws import router as ws_router
from app.api.simulation_ws import router as simulation_ws_router
from app.api.trips import router as trips_router
from app.api.alerts import router as alerts_router
from app.api.analytics_api import router as analytics_router
from app.api.alcohol import router as alcohol_router
from app.hardware.alcohol_sensor import mq3_serial_reader
from app.config import settings, validate_security_config
from app.database.connection import get_connection, init_db, seed_default_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise security config, database, preload models, and start MQ-3 sensor service."""
    # 1. Enforce security rules & environment checks
    validate_security_config()

    # 2. Database initialisation & migration
    conn = get_connection()
    init_db(conn)
    seed_default_data(conn)
    conn.close()

    # 3. Preload face recognition model before serving requests
    auth_module.warmup_detector()

    # 4. Start background MQ-3 sensor reader
    try:
        mq3_serial_reader.start()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Could not auto-start MQ-3 serial reader: %s", e)

    yield

    # Shutdown background MQ-3 reader
    try:
        mq3_serial_reader.stop()
    except Exception:
        pass


app = FastAPI(
    title="Fleet Safety Management API",
    description=(
        "Backend API for the Intelligent Driver Monitoring and Fleet Safety "
        "Management System for Commercial Vehicles."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow Vite dev server, frontend origin, and credentials for cookies
# ---------------------------------------------------------------------------
cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if settings.CORS_ORIGINS:
    for o in settings.CORS_ORIGINS.split(","):
        clean_o = o.strip()
        if clean_o and clean_o not in cors_origins:
            cors_origins.append(clean_o)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------------------------------------------------------------------
# Authentication & Resource Routers
# ---------------------------------------------------------------------------
app.include_router(owner_auth_router)
app.include_router(drivers_router)
app.include_router(vehicles_router)
app.include_router(auth_router)

# ---------------------------------------------------------------------------
# Phase 2+ routers (sessions, incidents, ws, trips, alerts, analytics)
# ---------------------------------------------------------------------------
app.include_router(monitoring_router)
app.include_router(incidents_router)
app.include_router(ws_router)
app.include_router(simulation_ws_router)
app.include_router(trips_router)
app.include_router(alerts_router)
app.include_router(analytics_router)
app.include_router(alcohol_router)


import os
from fastapi.staticfiles import StaticFiles
from app.config import settings

# ---------------------------------------------------------------------------
# Static Evidence Screenshot Mount
# ---------------------------------------------------------------------------
evidence_dir = os.path.join(str(settings.PROJECT_ROOT), "app", "evidence")
os.makedirs(evidence_dir, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=evidence_dir), name="evidence")

# ---------------------------------------------------------------------------
# Static Demo Videos Mount
# ---------------------------------------------------------------------------
demo_videos_dir = os.path.join(str(settings.PROJECT_ROOT), "data", "demo_videos")
os.makedirs(demo_videos_dir, exist_ok=True)
app.mount("/demo-videos", StaticFiles(directory=demo_videos_dir), name="demo_videos")


@app.get("/")
def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "Fleet Safety Management API",
        "version": "2.0.0",
    }


@app.get("/health")
def health():
    """API health check."""
    return {"status": "healthy"}


@app.get("/system/health")
def system_health():
    """Detailed health check of backend subsystems."""
    conn = get_connection()
    db_ok = True
    try:
        conn.execute("SELECT 1").fetchone()
    except Exception:
        db_ok = False
    finally:
        conn.close()

    model_ready, model_err = auth_module.is_model_ready()
    all_ok = db_ok and model_ready

    return {
        "status": "healthy" if all_ok else "degraded",
        "services": {
            "api": "online",
            "database": "connected" if db_ok else "disconnected",
            "face_recognition": "ready" if model_ready else ("error: " + str(model_err) if model_err else "uninitialized"),
            "drowsiness_engine": "ready",
            "websocket_pipeline": "available",
            "camera_interface": "browser_webcam",
        },
        "mode": "software_prototype",
    }

