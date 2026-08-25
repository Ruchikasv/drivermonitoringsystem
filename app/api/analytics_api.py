"""
Analytics REST endpoints — provides aggregate fleet safety metrics for the frontend analyticsService.

GET /analytics/metrics
GET /analytics/alerts-by-driver
GET /analytics/score-distribution
GET /analytics/drowsiness-trend
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.database.connection import get_connection
from app.database.driver_repository import DriverRepository
from app.database.monitoring_repository import MonitoringRepository
from app.database.vehicle_repository import VehicleRepository

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _get_repos(conn=Depends(get_connection)):
    yield conn, MonitoringRepository(conn), DriverRepository(conn), VehicleRepository(conn)


@router.get("/metrics")
def get_fleet_metrics(repos=Depends(_get_repos)) -> dict[str, Any]:
    """Summary KPI metrics across the fleet."""
    conn, m_repo, d_repo, v_repo = repos

    total_drivers = len(d_repo.get_all_drivers())
    active_sessions = len(m_repo.get_active_sessions())
    
    # Calculate total incidents and breakdown
    incidents = m_repo.get_all_incidents(limit=1000)
    total_incidents = len(incidents)
    critical_incidents = sum(1 for i in incidents if i.event_type.lower() == "critical")
    warning_incidents = sum(1 for i in incidents if i.event_type.lower() == "warning")
    nudge_incidents = sum(1 for i in incidents if i.event_type.lower() == "nudge")

    # Average fleet safety score
    ratings = conn.execute(
        "SELECT safety_score FROM driver_safety_ratings WHERE safety_score IS NOT NULL"
    ).fetchall()
    if ratings:
        avg_score = round(sum(r["safety_score"] for r in ratings) / len(ratings), 1)
    else:
        avg_score = 95.0

    return {
        "total_drivers": total_drivers,
        "active_trips": active_sessions,
        "total_incidents": total_incidents,
        "critical_incidents": critical_incidents,
        "warning_incidents": warning_incidents,
        "nudge_incidents": nudge_incidents,
        "average_safety_score": avg_score,
    }


@router.get("/alerts-by-driver")
def get_alerts_by_driver(repos=Depends(_get_repos)) -> list[dict[str, Any]]:
    """Return count of incidents per driver for the bar chart."""
    conn, m_repo, d_repo, v_repo = repos

    drivers = d_repo.get_all_drivers()
    result = []
    for d in drivers:
        d_incidents = m_repo.get_incidents_by_driver(d.driver_id)
        result.append({
            "name": d.name,
            "driver_id": d.driver_id,
            "count": len(d_incidents),
        })

    # If no real incidents across drivers, include at least all registered drivers with 0
    return result


@router.get("/score-distribution")
def get_score_distribution(repos=Depends(_get_repos)) -> list[dict[str, Any]]:
    """Distribution of driver safety scores across tiers for the Donut chart."""
    conn, m_repo, d_repo, v_repo = repos

    drivers = d_repo.get_all_drivers()
    excellent = 0  # 90-100
    good = 0       # 75-89
    moderate = 0   # 60-74
    critical = 0   # <60

    for d in drivers:
        rating = m_repo.get_safety_rating(d.driver_id)
        score = rating.safety_score if rating and rating.safety_score is not None else 100.0
        if score >= 90:
            excellent += 1
        elif score >= 75:
            good += 1
        elif score >= 60:
            moderate += 1
        else:
            critical += 1

    return [
        {"range": "90-100 (Excellent)", "count": max(1, excellent) if not drivers else excellent, "fill": "#10b981"},
        {"range": "75-89 (Good)", "count": good, "fill": "#3b82f6"},
        {"range": "60-74 (Moderate)", "count": moderate, "fill": "#f59e0b"},
        {"range": "<60 (Critical)", "count": critical, "fill": "#ef4444"},
    ]


@router.get("/drowsiness-trend")
def get_drowsiness_trend(repos=Depends(_get_repos)) -> list[dict[str, Any]]:
    """Daily trend of drowsiness incidents over the last 7 days."""
    conn, m_repo, d_repo, v_repo = repos

    incidents = m_repo.get_all_incidents(limit=1000)
    
    # Bucket by date
    days_map = {}
    today = datetime.now(timezone.utc).date()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        days_map[day.strftime("%a")] = {"date": day.strftime("%b %d"), "day": day.strftime("%a"), "critical": 0, "warning": 0, "nudge": 0}

    for inc in incidents:
        try:
            inc_date = datetime.fromisoformat(inc.timestamp).date()
            day_key = inc_date.strftime("%a")
            if day_key in days_map:
                tier = inc.event_type.lower()
                if tier in days_map[day_key]:
                    days_map[day_key][tier] += 1
        except Exception:
            pass

    return list(days_map.values())
