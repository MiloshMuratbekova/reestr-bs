"""Маршруты API."""

from fastapi import APIRouter

from app.api.routes import (
    algorithms,
    auth,
    health,
    listing,
    registry,
    reports,
    schedule,
    settings,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(registry.router)
api_router.include_router(listing.router)
api_router.include_router(algorithms.router)
api_router.include_router(reports.router)
api_router.include_router(schedule.router)
api_router.include_router(settings.router)

__all__ = ["api_router"]
