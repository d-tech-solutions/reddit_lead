"""Email channel, delivered through Resend's HTTP API."""

from __future__ import annotations

from html import escape

import httpx

from app.notifiers.base import (
    NotificationMessage,
    PermanentDeliveryError,
    TemporaryDeliveryError,
)

RESEND_URL = "https://api.resend.com/emails"


def render_subject(message: NotificationMessage) -> str:
    return f"New match in r/{message.subreddit}: {message.title}"[:200]


def render_text(message: NotificationMessage) -> str:
    parts = [
        f"Watcher: {message.watcher_name}",
        f"r/{message.subreddit}: {message.title}",
    ]
    if message.snippet:
        parts.append(message.snippet)
    if message.reason:
        parts.append(f"Why it matched: {message.reason}")
    parts.append(f"Open the post: {message.post_url}")
    parts.append(f"All matches: {message.feed_url}")
    return "\n\n".join(parts)


def render_html(message: NotificationMessage) -> str:
    snippet = f"<p>{escape(message.snippet)}</p>" if message.snippet else ""
    reason = (
        f"<p><strong>Why it matched:</strong> {escape(message.reason)}</p>" if message.reason else ""
    )
    return (
        f"<p>Your watcher <strong>{escape(message.watcher_name)}</strong> found a new post in "
        f"r/{escape(message.subreddit)}.</p>"
        f'<h3><a href="{escape(message.post_url)}">{escape(message.title)}</a></h3>'
        f"{snippet}{reason}"
        f'<p><a href="{escape(message.post_url)}">Open the post on Reddit</a> · '
        f'<a href="{escape(message.feed_url)}">See all matches</a></p>'
    )


class EmailNotifier:
    channel_type = "email"

    def __init__(self, api_key: str, from_address: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._from = from_address
        self._client = client or httpx.AsyncClient(timeout=15)

    async def send(self, destination: str, message: NotificationMessage) -> None:
        payload = {
            "from": self._from,
            "to": [destination],
            "subject": render_subject(message),
            "html": render_html(message),
            "text": render_text(message),
        }
        try:
            response = await self._client.post(
                RESEND_URL, json=payload, headers={"Authorization": f"Bearer {self._api_key}"}
            )
        except httpx.TransportError as error:
            raise TemporaryDeliveryError(f"resend unreachable: {error}") from error

        if response.status_code == 429 or response.status_code >= 500:
            raise TemporaryDeliveryError(f"resend {response.status_code}: {response.text[:200]}")
        if response.status_code >= 400:
            raise PermanentDeliveryError(f"resend {response.status_code}: {response.text[:200]}")

    async def close(self) -> None:
        await self._client.aclose()
