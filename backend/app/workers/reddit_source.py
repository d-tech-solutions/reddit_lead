"""Fetch recent posts from a subreddit, via either the official API or public RSS.

Both modes return the same dict shape so the ingestion worker is agnostic to which is active.
RSS needs no credentials and is meant for local dev while official API access is pending;
it omits post bodies, so production should run in "api" mode.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

import feedparser
import httpx

logger = logging.getLogger(__name__)

RSS_URL = "https://www.reddit.com/r/{subreddit}/new/.rss"


class PostSource(Protocol):
    async def fetch(self, subreddit: str, limit: int) -> list[dict[str, Any]]: ...

    async def close(self) -> None: ...


def _parse_rss_entry(entry: Any, subreddit: str) -> dict[str, Any] | None:
    # Reddit RSS ids look like "t3_abc123"; the bare base36 id is what the API returns.
    raw_id = getattr(entry, "id", "") or ""
    reddit_post_id = raw_id.split("_", 1)[1] if raw_id.startswith("t3_") else raw_id
    if not reddit_post_id:
        return None

    posted_at = None
    if getattr(entry, "updated", None):
        try:
            posted_at = datetime.fromisoformat(entry.updated)
        except ValueError:
            posted_at = None

    author = getattr(entry, "author", None)
    if author and author.startswith("/u/"):
        author = author[3:]

    return {
        "reddit_post_id": reddit_post_id,
        "subreddit": subreddit,
        "title": getattr(entry, "title", "") or "",
        "body": "",  # RSS gives rendered HTML, not the raw selftext the matcher wants
        "author": author,
        "permalink": getattr(entry, "link", "") or "",
        "posted_at": posted_at,
    }


class RssSource:
    def __init__(self, user_agent: str) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=20.0,
            follow_redirects=True,
        )

    async def fetch(self, subreddit: str, limit: int) -> list[dict[str, Any]]:
        response = await self._client.get(RSS_URL.format(subreddit=subreddit))
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        posts = [_parse_rss_entry(entry, subreddit) for entry in feed.entries[:limit]]
        return [post for post in posts if post is not None]

    async def close(self) -> None:
        await self._client.aclose()


def _parse_submission(submission: Any, subreddit: str) -> dict[str, Any]:
    created = getattr(submission, "created_utc", None)
    author = getattr(submission, "author", None)
    return {
        "reddit_post_id": submission.id,
        "subreddit": subreddit,
        "title": submission.title or "",
        "body": getattr(submission, "selftext", "") or "",
        "author": str(author) if author else None,
        "permalink": f"https://www.reddit.com{submission.permalink}",
        "posted_at": datetime.fromtimestamp(created, tz=UTC) if created else None,
    }


class ApiSource:
    def __init__(self, client_id: str, client_secret: str, user_agent: str) -> None:
        import asyncpraw

        self._reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        self._reddit.read_only = True

    async def fetch(self, subreddit: str, limit: int) -> list[dict[str, Any]]:
        sub = await self._reddit.subreddit(subreddit)
        return [_parse_submission(s, subreddit) async for s in sub.new(limit=limit)]

    async def close(self) -> None:
        await self._reddit.close()


def build_source(
    mode: str, client_id: str, client_secret: str, user_agent: str
) -> PostSource:
    if mode == "api":
        if not client_id or not client_secret:
            raise ValueError(
                "REDDIT_FETCH_MODE=api requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET"
            )
        return ApiSource(client_id, client_secret, user_agent)
    if mode == "rss":
        return RssSource(user_agent)
    raise ValueError(f"Unknown REDDIT_FETCH_MODE: {mode!r} (expected 'rss' or 'api')")
