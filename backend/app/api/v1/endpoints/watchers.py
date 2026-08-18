"""Watcher CRUD, scoped to the authenticated user."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.watcher import Watcher
from app.schemas.watcher import WatcherCreate, WatcherRead, WatcherUpdate
from app.services.limits import LimitExceeded, enforce_limits

router = APIRouter(prefix="/watchers", tags=["watchers"])


# Load one of the caller's watchers, or 404.
#
# 404 rather than 403 for someone else's watcher is deliberate: a 403 would confirm that the id
# exists, which lets an attacker enumerate other users' watchers.
async def _get_owned_watcher(
    session: AsyncSession, user: User, watcher_id: uuid.UUID
) -> Watcher:
    result = await session.execute(
        select(Watcher).where(Watcher.id == watcher_id, Watcher.user_id == user.id)
    )
    watcher = result.scalar_one_or_none()
    if watcher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watcher not found")
    return watcher


@router.get("", response_model=list[WatcherRead])
async def list_watchers(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Watcher]:
    result = await session.execute(
        select(Watcher).where(Watcher.user_id == user.id).order_by(Watcher.created_at.desc())
    )
    return list(result.scalars())


@router.post("", response_model=WatcherRead, status_code=status.HTTP_201_CREATED)
async def create_watcher(
    payload: WatcherCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Watcher:
    try:
        await enforce_limits(session, user, len(payload.subreddits), adding_watcher=True)
    except LimitExceeded as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.message) from error

    watcher = Watcher(
        user_id=user.id,
        name=payload.name,
        intent_text=payload.intent_text,
        subreddits=payload.subreddits,
        status=payload.status,
    )
    session.add(watcher)
    await session.commit()
    await session.refresh(watcher)
    return watcher


@router.get("/{watcher_id}", response_model=WatcherRead)
async def get_watcher(
    watcher_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Watcher:
    return await _get_owned_watcher(session, user, watcher_id)


@router.patch("/{watcher_id}", response_model=WatcherRead)
async def update_watcher(
    watcher_id: uuid.UUID,
    payload: WatcherUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Watcher:
    watcher = await _get_owned_watcher(session, user, watcher_id)

    if payload.subreddits is not None:
        try:
            await enforce_limits(
                session,
                user,
                len(payload.subreddits),
                adding_watcher=False,
                exclude_watcher_id=watcher.id,
            )
        except LimitExceeded as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=error.message
            ) from error
        watcher.subreddits = payload.subreddits

    if payload.name is not None:
        watcher.name = payload.name
    if payload.status is not None:
        watcher.status = payload.status
    # No embedding to invalidate: the verifier reads intent_text fresh on every call, so an edit
    # takes effect on the very next post the matcher considers.
    if payload.intent_text is not None:
        watcher.intent_text = payload.intent_text

    await session.commit()
    await session.refresh(watcher)
    return watcher


@router.delete("/{watcher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watcher(
    watcher_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    watcher = await _get_owned_watcher(session, user, watcher_id)
    # Its `matches` rows go too, via matches_watcher_id_fkey ON DELETE CASCADE.
    await session.delete(watcher)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
