"""The match feed: confirmed matches for the authenticated user, and read tracking.

Only `llm_verified IS TRUE` rows appear here. The table also holds every candidate the vector gate
produced — rejected and not-yet-verified — but those are calibration data, not product surface.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.match import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MatchPage,
    MatchPostRead,
    MatchRead,
    MatchWatcherRead,
)
from app.services import matches as service

router = APIRouter(prefix="/matches", tags=["matches"])


# Assemble one feed item from the three rows the join returned.
def _to_read(row: service.FeedRow) -> MatchRead:
    return MatchRead(
        id=row.match.id,
        matched_at=row.match.created_at,
        read_at=row.match.read_at,
        reason=row.match.llm_reason,
        watcher=MatchWatcherRead(id=row.watcher.id, name=row.watcher.name),
        post=MatchPostRead(
            reddit_post_id=row.post.reddit_post_id,
            subreddit=row.post.subreddit,
            title=row.post.title,
            author=row.post.author,
            permalink=row.post.permalink,
            posted_at=row.post.posted_at,
        ),
    )


@router.get("", response_model=MatchPage)
async def list_matches(
    watcher_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatchPage:
    try:
        decoded = service.decode_cursor(cursor) if cursor else None
    except service.InvalidCursor as error:
        # 400, not 500: a stale or hand-edited cursor is a bad request, and the client's recovery
        # is to drop it and reload from the top.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor"
        ) from error

    page = await service.fetch_feed(
        session, user.id, watcher_id=watcher_id, cursor=decoded, limit=limit
    )
    # Counted on every page so the badge stays honest after a mark-read elsewhere in the UI.
    unread = await service.unread_count(session, user.id)

    return MatchPage(
        items=[_to_read(row) for row in page.rows],
        next_cursor=page.next_cursor,
        unread=unread,
    )


# Mark one match as read. Returns the updated match so the UI can render from the response.
@router.post("/{match_id}/read", response_model=MatchRead)
async def mark_match_read(
    match_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatchRead:
    match = await service.get_owned_match(session, user.id, match_id)
    if match is None:
        # 404 for someone else's match, matching the watcher endpoints: a 403 would confirm the id
        # exists and make the table enumerable.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    await service.mark_read(session, match)

    # Re-read through the feed query so the response carries the post and watcher too, assembled
    # by the same path a feed item is.
    row = await service.fetch_one(session, user.id, match_id)
    if row is None:  # pragma: no cover — it existed a moment ago
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    return _to_read(row)


# Clear every unread match at once. Returns the new (zero) unread count for symmetry with the feed.
@router.post("/read-all")
async def mark_all_matches_read(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    updated = await service.mark_all_read(session, user.id)
    return {"updated": updated, "unread": 0}
