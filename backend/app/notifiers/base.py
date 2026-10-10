"""What every notification channel shares: the message, the error types, and the sender protocol.

Each channel (email, Slack, Telegram) turns the same `NotificationMessage` into its own format and
reports failure as one of two exceptions, so the notify worker can decide retry-versus-give-up
without knowing anything about any channel's API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models.match import Match
from app.models.matched_post import MatchedPost
from app.models.watcher import Watcher

# Enough of the post body to recognise it; the full text is one click away on Reddit.
SNIPPET_CHARS = 280


class TemporaryDeliveryError(Exception):
    """The channel is having a bad moment (timeout, rate limit, 5xx) — worth retrying."""


class PermanentDeliveryError(Exception):
    """Retrying cannot help (bad credentials, revoked webhook, blocked bot, bad address)."""


@dataclass(frozen=True)
class NotificationMessage:
    watcher_name: str
    subreddit: str
    title: str
    snippet: str
    reason: str
    post_url: str
    feed_url: str


class Notifier(Protocol):
    """Sends one message to one destination (an email address, a webhook URL, a chat id)."""

    channel_type: str

    async def send(self, destination: str, message: NotificationMessage) -> None: ...

    async def close(self) -> None: ...


def make_snippet(body: str) -> str:
    """Collapse whitespace and cut the post body down to a short teaser."""
    flat = " ".join((body or "").split())
    if len(flat) <= SNIPPET_CHARS:
        return flat
    return flat[: SNIPPET_CHARS - 1].rstrip() + "…"


def build_message(
    match: Match, post: MatchedPost, watcher: Watcher, frontend_url: str
) -> NotificationMessage:
    """Assemble the channel-neutral message for one confirmed match."""
    permalink = post.permalink
    # RSS mode stores a full link, API mode a full URL too — but guard a bare path just in case.
    post_url = permalink if permalink.startswith("http") else f"https://www.reddit.com{permalink}"
    return NotificationMessage(
        watcher_name=watcher.name,
        subreddit=post.subreddit,
        title=post.title,
        snippet=make_snippet(post.body),
        reason=match.llm_reason or "",
        post_url=post_url,
        feed_url=f"{frontend_url.rstrip('/')}/matches",
    )
