"""Response shapes for the matched-post feed (`/posts`, admin only).

Every post the LLM verifier confirmed for at least one watcher. Posts nobody matched are deleted
once judged, so unlike the old raw-ingest view nothing unmatched appears here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class PostRead(BaseModel):
    id: uuid.UUID
    reddit_post_id: str
    subreddit: str
    title: str
    body: str
    author: str | None
    permalink: str
    # Nullable because the RSS fetch mode does not always supply a timestamp.
    posted_at: datetime | None
    fetched_at: datetime


class PostPage(BaseModel):
    """One page plus the cursor for the next.

    `next_cursor` is null when the page is the last one.
    """

    items: list[PostRead]
    next_cursor: str | None
    # Every subreddit the caller can filter to — the union across their watchers, not just the
    # ones with a post on this page, so the UI can render the full chip set from page one.
    subreddits: list[str]
