"""Connecting a Telegram chat to a user: issue a one-time link, then match the bot's /start.

The user never types a chat id. They open `t.me/<bot>?start=<token>`, press Start, and Telegram
sends our webhook `/start <token>` along with the chat id. The token is the only thing tying that
anonymous chat to a PostPing account, so it is single-use, short-lived, and stored only as a hash.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_channel import NotificationChannel
from app.models.user import User
from app.services.settings import get_channel

TELEGRAM_CHANNEL = "telegram"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_link_token(session: AsyncSession, user: User, ttl_minutes: int) -> str:
    """Issue a fresh connect token, replacing any earlier one.

    An already-connected channel keeps working while a replacement link is pending: its
    destination and `verified` flag are untouched until the new /start actually arrives.
    """
    token = secrets.token_urlsafe(16)
    channel = await get_channel(session, user, TELEGRAM_CHANNEL)
    if channel is None:
        # Not verified until the user presses Start; the model default would say otherwise.
        channel = NotificationChannel(
            user_id=user.id, channel_type=TELEGRAM_CHANNEL, enabled=True, verified=False
        )
        session.add(channel)

    expires = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    # Reassigned rather than mutated: SQLAlchemy doesn't see in-place changes to a JSONB dict.
    channel.config = {
        **(channel.config or {}),
        "link_token_hash": hash_token(token),
        "link_expires_at": expires.isoformat(),
    }
    await session.commit()
    return token


async def complete_link(session: AsyncSession, token: str, chat_id: int) -> bool:
    """Attach `chat_id` to whichever channel issued `token`; False if unknown or expired."""
    result = await session.execute(
        select(NotificationChannel).where(
            NotificationChannel.channel_type == TELEGRAM_CHANNEL,
            NotificationChannel.config["link_token_hash"].astext == hash_token(token),
        )
    )
    channel = result.scalar_one_or_none()
    if channel is None or not channel.link_pending:
        return False

    config = {
        key: value
        for key, value in channel.config.items()
        if key not in ("link_token_hash", "link_expires_at")
    }
    config["destination"] = str(chat_id)
    channel.config = config
    channel.verified = True
    channel.enabled = True
    await session.commit()
    return True
