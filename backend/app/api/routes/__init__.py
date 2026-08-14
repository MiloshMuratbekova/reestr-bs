"""Маршруты API."""

from fastapi import APIRouter

from app.api.routes import algorithms, auth, health, registry, settings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(registry.router)
api_router.include_router(algorithms.router)
api_router.include_router(settings.router)

__all__ = ["api_router"]
