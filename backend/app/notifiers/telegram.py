"""Telegram channel, delivered by our bot to a chat that opened a conversation with it."""

from __future__ import annotations

from html import escape

import httpx

from app.notifiers.base import (
    NotificationMessage,
    PermanentDeliveryError,
    TemporaryDeliveryError,
)

API_BASE = "https://api.telegram.org"
# Telegram rejects messages over 4096 characters; titles are the only unbounded part we send.
MAX_TITLE_CHARS = 300


def render_text(message: NotificationMessage) -> str:
    """Format a match as Telegram HTML. Post text is escaped so it can't inject markup."""
    title = escape(message.title[:MAX_TITLE_CHARS])
    lines = [
        f"<b>New match in r/{escape(message.subreddit)}</b> · {escape(message.watcher_name)}",
        f'<a href="{escape(message.post_url)}">{title}</a>',
    ]
    if message.snippet:
        lines.append(escape(message.snippet))
    if message.reason:
        lines.append(f"<i>Why it matched: {escape(message.reason)}</i>")
    return "\n\n".join(lines)


class TelegramNotifier:
    channel_type = "telegram"

    def __init__(self, bot_token: str, client: httpx.AsyncClient | None = None):
        self._token = bot_token
        self._client = client or httpx.AsyncClient(timeout=15)

    async def send(self, destination: str, message: NotificationMessage) -> None:
        await self.send_text(destination, render_text(message))

    async def send_text(self, chat_id: str, html: str) -> None:
        """Send raw Telegram-HTML text to a chat; used for matches and for the bot's own replies."""
        payload = {
            "chat_id": chat_id,
            "text": html,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        try:
            response = await self._client.post(f"{API_BASE}/bot{self._token}/sendMessage", json=payload)
        except httpx.TransportError as error:
            # Only the exception's class: its text can carry the request URL, which holds the token.
            raise TemporaryDeliveryError(f"telegram unreachable: {type(error).__name__}") from error

        if response.status_code == 429 or response.status_code >= 500:
            raise TemporaryDeliveryError(f"telegram {response.status_code}: {response.text[:200]}")
        if response.status_code == 401:
            # Our bot token is wrong — that's our misconfiguration, not the user's chat, so don't
            # tell the worker to flag the user's channel as dead.
            raise TemporaryDeliveryError("telegram 401: bot token rejected")
        if response.status_code != 200:
            # 400 chat not found, 403 user blocked the bot or deleted the chat.
            raise PermanentDeliveryError(f"telegram {response.status_code}: {response.text[:200]}")

    async def close(self) -> None:
        await self._client.aclose()
