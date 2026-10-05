"""Feed queries for raw ingested Reddit posts.

`reddit_posts` carries no `user_id` of its own — the ingestion worker fetches a subreddit once for
every watcher that references it, regardless of who owns them. So "which posts can this user see"
is answered by joining through the caller's own watchers' subreddit lists rather than a foreign
key, the same way `matches.py` answers "which matches" through `watchers.user_id`.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reddit_post import RedditPost
from app.models.watcher import Watcher


class InvalidCursor(ValueError):
    """Raised for a cursor that is malformed, truncated, or not ours."""


@dataclass(frozen=True)
class Cursor:
    """Where the previous page stopped: the last row's sort key, in full.

    Both halves are needed — `fetched_at` alone is not unique, since the ingestion worker inserts
    a batch per poll and rows can share a timestamp to the microsecond.
    """

    fetched_at: datetime
    post_id: uuid.UUID


def encode_cursor(fetched_at: datetime, post_id: uuid.UUID) -> str:
    raw = f"{fetched_at.isoformat()}|{post_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(value: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(value.encode()).decode()
        timestamp, _, identifier = raw.partition("|")
        return Cursor(fetched_at=datetime.fromisoformat(timestamp), post_id=uuid.UUID(identifier))
    except (ValueError, binascii.Error, UnicodeDecodeError) as error:
        raise InvalidCursor("Invalid cursor") from error


# The subreddits this user's watchers cover, deduplicated. Drives both the visible post scope and
# the chip selector — a user has no reason to browse a subreddit none of their watchers follows.
async def watched_subreddits(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await session.execute(select(Watcher.subreddits).where(Watcher.user_id == user_id))
    subreddits: set[str] = set()
    for row in result.scalars():
        subreddits.update(row)
    return sorted(subreddits)


# Every subreddit ever ingested, for the admin pipeline view — unlike `watched_subreddits`, not
# scoped to any one user's watchers, since an admin is checking the whole pipeline's intake.
async def distinct_subreddits(session: AsyncSession) -> list[str]:
    result = await session.execute(select(RedditPost.subreddit).distinct())
    return sorted(result.scalars())


def _posts_query(subreddits: list[str], subreddit: str | None) -> Select:
    query = select(RedditPost).where(RedditPost.subreddit.in_(subreddits))
    # Note this narrows an already subreddit-scoped query. Filtering on `subreddit` *instead of*
    # the caller's watched list would let anyone read any subreddit's posts by guessing a name.
    if subreddit is not None:
        query = query.where(RedditPost.subreddit == subreddit)
    return query


@dataclass(frozen=True)
class PostPage:
    items: list[RedditPost]
    next_cursor: str | None


# Read one page of ingested posts, most-recently-fetched first.
#
# `subreddits` is the caller's full watched set — pass the same list regardless of the `subreddit`
# filter, since an empty list here (no watchers yet) should short-circuit rather than reach the DB.
async def fetch_posts(
    session: AsyncSession,
    subreddits: list[str],
    subreddit: str | None = None,
    cursor: Cursor | None = None,
    limit: int = 20,
) -> PostPage:
    if not subreddits:
        return PostPage(items=[], next_cursor=None)

    query = _posts_query(subreddits, subreddit)

    # Keyset paging, not OFFSET — see `matches.py` for why: new posts arrive at the head of this
    # feed continuously, and an OFFSET window shifts under that with every insert.
    if cursor is not None:
        query = query.where(
            tuple_(RedditPost.fetched_at, RedditPost.id) < (cursor.fetched_at, cursor.post_id)
        )

    query = query.order_by(RedditPost.fetched_at.desc(), RedditPost.id.desc()).limit(limit + 1)
    result = await session.execute(query)
    rows = list(result.scalars())

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = encode_cursor(rows[-1].fetched_at, rows[-1].id) if has_more and rows else None
    return PostPage(items=rows, next_cursor=next_cursor)
