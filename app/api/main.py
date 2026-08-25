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
from app.api.auth import router as auth_router
from app.api.monitoring import router as monitoring_router
from app.api.incidents import router as incidents_router
from app.api.monitoring_ws import router as ws_router
from app.api.trips import router as trips_router
from app.api.alerts import router as alerts_router
from app.api.analytics_api import router as analytics_router
from app.database.connection import get_connection, init_db, seed_default_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the SQLite database on startup."""
    conn = get_connection()
    init_db(conn)
    seed_default_data(conn)
    conn.close()
    yield


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
# CORS — allow the Vite dev server and any LAN client
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Phase 1 & Auth routers
# ---------------------------------------------------------------------------
app.include_router(drivers_router)
app.include_router(vehicles_router)
app.include_router(auth_router)

# ---------------------------------------------------------------------------
# Phase 2+ routers (sessions, incidents, ws, trips, alerts, analytics)
# ---------------------------------------------------------------------------
app.include_router(monitoring_router)
app.include_router(incidents_router)
app.include_router(ws_router)
app.include_router(trips_router)
app.include_router(alerts_router)
app.include_router(analytics_router)


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