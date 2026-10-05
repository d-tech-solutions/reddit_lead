"""The raw post feed: everything the ingestion worker has pulled from Reddit.

Unlike `/matches`, nothing here has been through the vector gate or the LLM verifier — this is
what's actually flowing into the pipeline before any matching happens. Admin-only: it spans every
ingested subreddit, not just the caller's own watchers, so it doubles as visibility into what's
being sent to the AI verifier for analysis.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_superadmin
from app.db.session import get_db
from app.models.reddit_post import RedditPost
from app.models.user import User
from app.schemas.post import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PostPage, PostRead
from app.services import posts as service

router = APIRouter(prefix="/posts", tags=["posts"])


def _to_read(post: RedditPost) -> PostRead:
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
