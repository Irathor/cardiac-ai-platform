"""Aggregates every /api/v1 router. Feature routers are added here as each phase lands."""
from fastapi import APIRouter

from app.api.v1 import (
    analysis,
    annotations,
    auth,
    datasets,
    health,
    imaging,
    models,
    patients,
    studies,
    training,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(patients.router, prefix="/patients", tags=["patients"])
api_router.include_router(studies.router, prefix="/studies", tags=["studies"])
api_router.include_router(imaging.router, tags=["imaging"])
api_router.include_router(analysis.router, tags=["analysis"])
api_router.include_router(annotations.router, tags=["annotations"])
api_router.include_router(datasets.router, tags=["datasets"])
api_router.include_router(training.router, tags=["training"])
api_router.include_router(models.router, tags=["models"])
