"""Slack channel, delivered to a user-supplied incoming-webhook URL."""

from __future__ import annotations

import re

import httpx

from app.notifiers.base import (
    NotificationMessage,
    PermanentDeliveryError,
    TemporaryDeliveryError,
)

# Only real Slack webhook hosts are accepted. The URL is user-supplied and our server posts to it,
# so anything looser would let a user aim the worker at an arbitrary (e.g. internal) address.
WEBHOOK_URL_PATTERN = re.compile(r"^https://hooks\.slack\.com/(services|workflows)/[A-Za-z0-9/_-]+$")


def is_valid_webhook_url(url: str) -> bool:
    return bool(WEBHOOK_URL_PATTERN.fullmatch(url))


def escape_mrkdwn(text: str) -> str:
    """Escape the three characters Slack treats as control syntax in message text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_payload(message: NotificationMessage) -> dict:
    title = escape_mrkdwn(message.title)
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*<{message.post_url}|{title}>*\nr/{escape_mrkdwn(message.subreddit)}"
                f" · watcher: {escape_mrkdwn(message.watcher_name)}",
            },
        }
    ]
    if message.snippet:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": escape_mrkdwn(message.snippet)}}
        )
    if message.reason:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Why it matched: {escape_mrkdwn(message.reason)}"}
                ],
            }
        )
    return {
        # Shown in notifications and anywhere blocks aren't rendered.
        "text": escape_mrkdwn(f"New match in r/{message.subreddit}: {message.title}"),
        "blocks": blocks,
    }


class SlackNotifier:
    channel_type = "slack"

    def __init__(self, client: httpx.AsyncClient | None = None):
        # No redirects: a webhook that redirects somewhere else is not one we should follow.
        self._client = client or httpx.AsyncClient(timeout=15, follow_redirects=False)

    async def send(self, destination: str, message: NotificationMessage) -> None:
        if not is_valid_webhook_url(destination):
            raise PermanentDeliveryError("destination is not a Slack webhook URL")
        try:
            response = await self._client.post(destination, json=render_payload(message))
        except httpx.TransportError as error:
            raise TemporaryDeliveryError(f"slack unreachable: {error}") from error

        if response.status_code == 429 or response.status_code >= 500:
            raise TemporaryDeliveryError(f"slack {response.status_code}: {response.text[:200]}")
        if response.status_code != 200:
            # 400/403/404/410: invalid payload, revoked webhook, archived channel — retrying won't help.
            raise PermanentDeliveryError(f"slack {response.status_code}: {response.text[:200]}")

    async def close(self) -> None:
        await self._client.aclose()
