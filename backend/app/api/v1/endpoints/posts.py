"""The matched-post feed: every post the LLM verifier confirmed for at least one watcher.

Unlike `/matches` (one row per watcher, scoped to the caller), this is one row per Reddit post
across all users, so it is admin-only. Posts nobody matched are deleted once judged and never
appear here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_superadmin
from app.db.session import get_db
from app.models.matched_post import MatchedPost
from app.models.user import User
from app.schemas.post import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PostPage, PostRead
from app.services import posts as service

router = APIRouter(prefix="/posts", tags=["posts"])


def _to_read(post: MatchedPost) -> PostRead:
    return PostRead(
        id=post.id,
        reddit_post_id=post.reddit_post_id,
        subreddit=post.subreddit,
        title=post.title,
        body=post.body,
        author=post.author,
        permalink=post.permalink,
        posted_at=post.posted_at,
        fetched_at=post.fetched_at,
    )


@router.get("", response_model=PostPage)
async def list_posts(
    subreddit: str | None = None,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_superadmin),
) -> PostPage:
    try:
        decoded = service.decode_cursor(cursor) if cursor else None
    except service.InvalidCursor as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor"
        ) from error

    subreddits = await service.distinct_subreddits(session)
    # A subreddit nothing has ingested narrows to nothing rather than falling back to "everything"
    # — same reasoning as the watcher_id filter on /matches.
    if subreddit is not None and subreddit not in subreddits:
        return PostPage(items=[], next_cursor=None, subreddits=subreddits)

    page = await service.fetch_posts(
        session, subreddits, subreddit=subreddit, cursor=decoded, limit=limit
    )

    return PostPage(
        items=[_to_read(post) for post in page.items],
        next_cursor=page.next_cursor,
        subreddits=subreddits,
    )
