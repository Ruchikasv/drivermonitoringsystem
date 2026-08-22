"""
FastAPI application entry point for the Driver Monitoring System.

Phase 1 API:
- Driver information
- Driver profile
- Vehicle assignment

Drowsiness monitoring and sensor APIs will be added in later phases.
"""
from app.api.drivers import router as drivers_router
from app.api.vehicles import router as vehicles_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.connection import get_connection, init_db

app = FastAPI(
    title="Fleet Safety Management API",
    description="Backend API for the Driver Monitoring and Fleet Safety System",
    version="1.0.0",
)

# Enable CORS for frontend development and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(drivers_router)
app.include_router(vehicles_router)


@app.on_event("startup")
def startup() -> None:
    """Initialise the SQLite database when the API starts."""
    conn = get_connection()
    init_db(conn)
    conn.close()


@app.get("/")
def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "Fleet Safety Management API",
        "phase": "Phase 1.5",
    }


@app.get("/health")
def health():
    """API health check."""
    return {"status": "healthy"}