"""Analytics dashboard data for the authenticated user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import DEFAULT_DAYS, MAX_DAYS, MIN_DAYS, Analytics
from app.services import analytics as service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=Analytics)
async def get_analytics(
    days: int = Query(DEFAULT_DAYS, ge=MIN_DAYS, le=MAX_DAYS),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Analytics:
    return await service.build_analytics(session, user.id, days)
