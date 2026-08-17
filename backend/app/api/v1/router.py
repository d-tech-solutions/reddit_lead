from fastapi import APIRouter

from app.api.v1.endpoints import health, matches, users, watchers

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(users.router)
api_router.include_router(watchers.router)
api_router.include_router(matches.router)
