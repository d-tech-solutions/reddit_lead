"""Superadmin user management: list, inspect, activate/deactivate, change plan, delete.

Every route depends on `require_superadmin`, so a non-admin gets a 403 before any handler runs.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_superadmin
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin import AdminUserDetail, AdminUserRead, AdminUserUpdate
from app.schemas.watcher import WatcherRead
from app.services import admin as service
from app.services.account import delete_account

router = APIRouter(prefix="/admin", tags=["admin"])


# `watcher_count` isn't a column on `User`, so it can't come from `model_validate`'s attribute
# lookup — build the response explicitly instead.
def _to_read(user: User, watcher_count: int) -> AdminUserRead:
    return AdminUserRead(
        id=user.id,
        email=user.email,
        plan=user.plan,
        is_active=user.is_active,
        is_superadmin=user.is_superadmin,
        created_at=user.created_at,
        watcher_count=watcher_count,
    )


# A target user acting on themselves through this API is almost always a mistake — deactivating or
# deleting yourself here would lock out the only account that could undo it. Point them at the
# normal self-service routes instead.
def _reject_self_target(admin: User, target_id: uuid.UUID) -> None:
    if admin.id == target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manage your own account from Settings, not the admin panel.",
        )


async def _get_target_or_404(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await service.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/users", response_model=list[AdminUserRead])
async def list_users(
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_superadmin),
) -> list[AdminUserRead]:
    rows = await service.list_users(session, search=search, limit=limit, offset=offset)
    return [_to_read(row.user, row.watcher_count) for row in rows]


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_superadmin),
) -> AdminUserDetail:
    user = await _get_target_or_404(session, user_id)
    watchers = await service.list_user_watchers(session, user_id)
    return AdminUserDetail(
        **_to_read(user, len(watchers)).model_dump(),
        watchers=[WatcherRead.model_validate(watcher) for watcher in watchers],
    )


@router.patch("/users/{user_id}", response_model=AdminUserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    session: AsyncSession = Depends(get_db),
    admin: User = Depends(require_superadmin),
) -> AdminUserRead:
    _reject_self_target(admin, user_id)
    user = await _get_target_or_404(session, user_id)

    if payload.plan is not None:
        try:
            service.set_user_plan(user, payload.plan)
        except service.UnknownPlan as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
            ) from error

    if payload.is_active is not None:
        await service.set_user_active(session, user, payload.is_active)

    await session.commit()
    await session.refresh(user)
    watchers = await service.list_user_watchers(session, user_id)
    return _to_read(user, len(watchers))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin: User = Depends(require_superadmin),
) -> Response:
    _reject_self_target(admin, user_id)
    user = await _get_target_or_404(session, user_id)
    await delete_account(session, settings, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
