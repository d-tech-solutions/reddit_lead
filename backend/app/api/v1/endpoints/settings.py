"""Notification settings for the current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.notification_channel import NotificationChannel
from app.models.user import User
from app.schemas.settings import NotificationChannelRead, SettingsRead, SettingsUpdate
from app.services.settings import get_or_create_email_channel, update_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _settings_read(user: User, channel: NotificationChannel) -> SettingsRead:
    return SettingsRead(
        account_email=user.email,
        notification_email=user.notification_email,
        channels=[NotificationChannelRead.model_validate(channel)],
    )


@router.get("", response_model=SettingsRead)
async def read_settings(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SettingsRead:
    channel = await get_or_create_email_channel(session, user)
    return _settings_read(user, channel)


@router.patch("", response_model=SettingsRead)
async def patch_settings(
    payload: SettingsUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SettingsRead:
    user, channel = await update_settings(session, user, payload)
    return _settings_read(user, channel)
