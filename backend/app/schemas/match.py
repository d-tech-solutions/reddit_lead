"""Response shapes for the match feed.

A match is only interesting alongside the post it found and the watcher that caught it, so the
read model embeds both. That keeps the feed a single round trip instead of N+1 lookups from the
UI, and it is why these are hand-written rather than a `from_attributes` mirror of the ORM row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

# One page of the feed. Small because each item carries a post title and a verifier sentence, and
# because the UI's "load more" is cheap — see `MAX_PAGE_SIZE` for the ceiling a caller can ask for.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class MatchPostRead(BaseModel):
    """The Reddit post, trimmed to what the feed renders.

    The body is omitted on purpose: it can run to thousands of characters, the card only shows a
    title, and `permalink` is one click away for the full thing.
    """

    reddit_post_id: str
    subreddit: str
    title: str
    author: str | None
    permalink: str
    # Nullable because the RSS fetch mode does not always supply a timestamp — which is also why
    # the feed sorts on the match's own `created_at` rather than on this.
    posted_at: datetime | None


class MatchWatcherRead(BaseModel):
    """Just enough of the watcher to answer "why am I being shown this?"."""

    id: uuid.UUID
    name: str


class MatchRead(BaseModel):
    id: uuid.UUID
    # When the verifier confirmed it, not when the post was written. The feed's sort key.
    matched_at: datetime
    read_at: datetime | None
    # The verifier's own sentence. Shown to the user: a match with a stated reason is checkable,
    # and a wrong one is reportable.
    reason: str | None
    watcher: MatchWatcherRead
    post: MatchPostRead


class MatchPage(BaseModel):
    """One page plus the cursor for the next.

    `next_cursor` is null when the page is the last one. Callers should page until it is null
    rather than until a short page arrives — the two are not the same when a page is exactly full.
    """

    items: list[MatchRead]
    next_cursor: str | None
    unread: int
