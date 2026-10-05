"""Settings read/update, plus lazily creating a user's default email channel."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_channel import NotificationChannel
from app.models.user import User
from app.schemas.settings import SettingsUpdate

EMAIL_CHANNEL = "email"


# Find the caller's email channel row, creating it on first sight.
#
# Same race-safe shape as `get_or_create_user` in api/deps.py: two concurrent first-reads can both
# try to insert, so a unique-violation on (user_id, channel_type) is treated as "someone else just
# created it" and re-read, rather than surfacing as a 500.
async def get_or_create_email_channel(session: AsyncSession, user: User) -> NotificationChannel:
    result = await session.execute(
        select(NotificationChannel).where(
            NotificationChannel.user_id == user.id,
            NotificationChannel.channel_type == EMAIL_CHANNEL,
        )
    )
    channel = result.scalar_one_or_none()
    if channel is not None:
        return channel

    channel = NotificationChannel(user_id=user.id, channel_type=EMAIL_CHANNEL)
    session.add(channel)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(NotificationChannel).where(
                NotificationChannel.user_id == user.id,
                NotificationChannel.channel_type == EMAIL_CHANNEL,
            )
        )
        channel = result.scalar_one()
    else:
        await session.refresh(channel)

    return channel


async def update_settings(
    session: AsyncSession, user: User, payload: SettingsUpdate
) -> tuple[User, NotificationChannel]:
    channel = await get_or_create_email_channel(session, user)

    user.notification_email = payload.notification_email
    channel.enabled = payload.email_enabled

    await session.commit()
    await session.refresh(user)
    await session.refresh(channel)
    return user, channel
