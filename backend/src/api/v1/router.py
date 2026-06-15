"""
API v1 Router - aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from src.api.v1.endpoints.auth_controller import router as auth_router
from src.api.v1.endpoints.health_controller import router as health_router
from src.api.v1.endpoints.user_controller import router as user_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(user_router)
api_v1_router.include_router(health_router)
