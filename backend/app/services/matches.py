"""Feed queries for confirmed matches.

Kept out of the endpoint module for the same reason as `limits.py`: the interesting parts here are
the ownership join and the cursor arithmetic, and both are worth testing without HTTP in the way.

Every query in this module joins `matches -> watchers` and filters on `watchers.user_id`. There is
no other ownership link — `matches` has no `user_id` column of its own — so dropping that join
silently exposes every user's feed to every user.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.matched_post import MatchedPost
from app.models.watcher import Watcher


class InvalidCursor(ValueError):
    """Raised for a cursor that is malformed, truncated, or not ours."""


@dataclass(frozen=True)
class Cursor:
    """Where the previous page stopped: the last row's sort key, in full.

    Both halves are needed. `created_at` alone is not unique — the matcher writes several rows in
    one transaction and they can share a timestamp to the microsecond — so paging on it alone
    would drop whichever siblings landed after the page boundary.
    """

    created_at: datetime
    match_id: uuid.UUID


# Pack a cursor into something opaque enough that callers do not build one by hand.
#
# base64 rather than a raw "timestamp,uuid" string: the encoding is not a security measure (it is
# trivially reversible), it just discourages clients from constructing cursors themselves and then
# breaking when the sort key changes.
def encode_cursor(created_at: datetime, match_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{match_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


# Unpack a cursor, rejecting anything we did not produce.
# Every failure mode collapses to InvalidCursor so the endpoint can answer 400 rather than 500.
def decode_cursor(value: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(value.encode()).decode()
        timestamp, _, identifier = raw.partition("|")
        return Cursor(created_at=datetime.fromisoformat(timestamp), match_id=uuid.UUID(identifier))
    except (ValueError, binascii.Error, UnicodeDecodeError) as error:
        raise InvalidCursor("Invalid cursor") from error


# Build the base feed query: this user's matches, with post and watcher attached. Every row in
# `matches` is a confirmed match — rejections are never stored there.
def _feed_query(user_id: uuid.UUID, watcher_id: uuid.UUID | None) -> Select:
    query = (
        select(Match, Watcher, MatchedPost)
        .join(Watcher, Match.watcher_id == Watcher.id)
        .join(MatchedPost, Match.matched_post_id == MatchedPost.id)
        .where(Watcher.user_id == user_id)
    )
    # Note this narrows an already user-scoped query. Filtering on watcher_id *instead of*
    # user_id would let anyone read anyone's feed by guessing an id.
    if watcher_id is not None:
        query = query.where(Match.watcher_id == watcher_id)
    return query


@dataclass(frozen=True)
class FeedRow:
    match: Match
    watcher: Watcher
    post: MatchedPost


@dataclass(frozen=True)
class FeedPage:
    rows: list[FeedRow]
    next_cursor: str | None


# Read one page of the feed, newest first.
#
# Fetches `limit + 1` rows: the extra one is never returned, it only answers "is there a next
# page?" without a second COUNT over the whole feed.
async def fetch_feed(
    session: AsyncSession,
    user_id: uuid.UUID,
    watcher_id: uuid.UUID | None = None,
    cursor: Cursor | None = None,
    limit: int = 20,
) -> FeedPage:
    query = _feed_query(user_id, watcher_id)

    # Keyset paging, not OFFSET. Matches arrive at the head of this feed continuously, and every
    # insert shifts an OFFSET window by one — the user sees a row twice or not at all. Comparing
    # against the last row's sort key is immune to that.
    if cursor is not None:
        query = query.where(
            tuple_(Match.created_at, Match.id) < (cursor.created_at, cursor.match_id)
        )

    query = query.order_by(Match.created_at.desc(), Match.id.desc()).limit(limit + 1)
    result = await session.execute(query)
    records = list(result.all())

    has_more = len(records) > limit
    records = records[:limit]

    rows = [FeedRow(match=match, watcher=watcher, post=post) for match, watcher, post in records]
    next_cursor = (
        encode_cursor(rows[-1].match.created_at, rows[-1].match.id) if has_more and rows else None
    )
    return FeedPage(rows=rows, next_cursor=next_cursor)


# Count confirmed matches the user has not opened yet. Drives the nav badge.
async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Match)
        .join(Watcher, Match.watcher_id == Watcher.id)
        .where(Watcher.user_id == user_id, Match.read_at.is_(None))
    )
    return int(result.scalar_one())


# Load one of the caller's matches, or None.
#
# Returns None rather than raising so the endpoint owns the HTTP shape — and it answers 404 for
# someone else's match, which is why this filters on user_id rather than trusting the id alone.
async def get_owned_match(
    session: AsyncSession, user_id: uuid.UUID, match_id: uuid.UUID
) -> Match | None:
    result = await session.execute(
        select(Match)
        .join(Watcher, Match.watcher_id == Watcher.id)
        .where(Match.id == match_id, Watcher.user_id == user_id)
    )
    return result.scalar_one_or_none()


# Load a single match with its post and watcher attached — the feed's row shape, for one id.
# Used after a mutation so the response can be assembled the same way a feed item is.
async def fetch_one(
    session: AsyncSession, user_id: uuid.UUID, match_id: uuid.UUID
) -> FeedRow | None:
    result = await session.execute(_feed_query(user_id, None).where(Match.id == match_id))
    record = result.first()
    if record is None:
        return None
    match, watcher, post = record
    return FeedRow(match=match, watcher=watcher, post=post)


# Stamp a match as read, leaving an already-read one alone.
#
# Idempotent on purpose: the UI marks on open, and re-opening a match should not rewrite the
# timestamp — "when did I first see this" is the useful reading of the column.
async def mark_read(session: AsyncSession, match: Match) -> Match:
    if match.read_at is None:
        match.read_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(match)
    return match


# Clear the whole unread badge in one statement. Returns how many rows it touched.
async def mark_all_read(session: AsyncSession, user_id: uuid.UUID) -> int:
    owned = select(Watcher.id).where(Watcher.user_id == user_id)
    result = await session.execute(
        update(Match)
        .where(Match.watcher_id.in_(owned), Match.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()
    return int(result.rowcount or 0)
