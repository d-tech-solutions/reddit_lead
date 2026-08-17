"""Watcher CRUD, scoped to the authenticated user."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.watcher import Watcher
from app.schemas.watcher import WatcherCreate, WatcherRead, WatcherUpdate
from app.services.limits import LimitExceeded, enforce_limits

logger = logging.getLogger(__name__)

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


# Ask the embedding worker to (re)embed a watcher's intent text.
#
# Non-fatal by design, matching the other queue hand-offs: the embedding worker's backfill sweep
# picks up any watcher whose `intent_embedding` is NULL, so a failed enqueue costs latency, not
# correctness.
async def _enqueue_embed(request: Request, watcher_id: uuid.UUID) -> None:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return
    try:
        await redis.enqueue_job(
            "embed_watcher", str(watcher_id), _job_id=f"embed_watcher:{watcher_id}"
        )
    except Exception:
        logger.exception("watchers: failed enqueueing embed job for %s", watcher_id)


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
    request: Request,
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
        direction=payload.direction,
        status=payload.status,
    )
    session.add(watcher)
    await session.commit()
    await session.refresh(watcher)

    await _enqueue_embed(request, watcher.id)
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
    request: Request,
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
    if payload.direction is not None:
        watcher.direction = payload.direction
    if payload.status is not None:
        watcher.status = payload.status

    # Changing the intent invalidates the stored vector. Clearing it in the same transaction closes
    # the window where the matcher would otherwise compare posts against the *old* wording: the
    # matcher only considers watchers with a non-NULL embedding, so it skips this one until the
    # embedding worker catches up.
    intent_changed = payload.intent_text is not None and payload.intent_text != watcher.intent_text
    if intent_changed:
        watcher.intent_text = payload.intent_text
        watcher.intent_embedding = None
        watcher.embedded_at = None

    await session.commit()
    await session.refresh(watcher)

    if intent_changed:
        await _enqueue_embed(request, watcher.id)
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
