from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    analytics,
    billing,
    health,
    matches,
    posts,
    settings,
    telegram,
    users,
    watchers,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(users.router)
api_router.include_router(watchers.router)
api_router.include_router(matches.router)
api_router.include_router(analytics.router)
api_router.include_router(posts.router)
api_router.include_router(settings.router)
api_router.include_router(telegram.router)
api_router.include_router(billing.router)
api_router.include_router(admin.router)
