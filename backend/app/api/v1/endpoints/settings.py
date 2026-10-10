"""Notification settings for the current user."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.constants import channel_allowed
from app.core.crypto import EncryptionNotConfigured, UndecryptableSecret
from app.db.session import get_db
from app.models.notification_channel import NotificationChannel
from app.models.user import User
from app.notifiers import build_notifiers
from app.notifiers.base import (
    NotificationMessage,
    Notifier,
    PermanentDeliveryError,
    TemporaryDeliveryError,
)
from app.schemas.settings import (
    ChannelUpdate,
    NotificationChannelRead,
    SettingsRead,
    SettingsUpdate,
    SlackConnect,
    TelegramLinkRead,
)
from app.services import settings as service
from app.services import telegram as telegram_service
from app.workers.notify import resolve_destination

router = APIRouter(prefix="/settings", tags=["settings"])

TEST_MESSAGE = NotificationMessage(
    watcher_name="Test watcher",
    subreddit="postping",
    title="This is a test notification from PostPing",
    snippet="If you can read this, alerts for your matches will arrive here.",
    reason="You asked for a test message.",
    post_url="https://www.reddit.com/",
    feed_url="",
)


async def _settings_read(session: AsyncSession, user: User) -> SettingsRead:
    channels = await service.list_channels(session, user)
    return SettingsRead(
        account_email=user.email,
        notification_email=user.notification_email,
        channels=[NotificationChannelRead.model_validate(channel) for channel in channels],
    )


async def get_notifiers() -> AsyncIterator[dict[str, Notifier]]:
    """The configured notifiers for a one-off test send, closed when the request ends."""
    notifiers = build_notifiers(get_settings())
    try:
        yield notifiers
    finally:
        for notifier in notifiers.values():
            await notifier.close()


def _require_encryption_key() -> str:
    key = get_settings().NOTIFY_ENCRYPTION_KEY
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack isn't available on this server yet (encryption key not configured).",
        )
    return key


def _require_plan_for(user: User, channel_type: str) -> None:
    if not channel_allowed(user.plan, channel_type):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{channel_type.capitalize()} alerts are available on paid plans.",
        )


async def _existing_channel(
    session: AsyncSession, user: User, channel_type: str
) -> NotificationChannel:
    channel = await service.get_channel(session, user, channel_type)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not connected")
    return channel


async def _deliver_test(
    notifier: Notifier | None, channel_type: str, destination: str | None
) -> None:
    """Send the sample message, translating delivery failures into API errors."""
    name = channel_type.capitalize()
    if notifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{name} delivery isn't configured on this server.",
        )
    if not destination:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No destination is set for this channel."
        )
    try:
        await notifier.send(destination, TEST_MESSAGE)
    except PermanentDeliveryError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} rejected the message: {error}"
        ) from error
    except TemporaryDeliveryError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Couldn't reach {name} right now, try again: {error}",
        ) from error


@router.get("", response_model=SettingsRead)
async def read_settings(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SettingsRead:
    await service.get_or_create_email_channel(session, user)
    return await _settings_read(session, user)


@router.patch("", response_model=SettingsRead)
async def patch_settings(
    payload: SettingsUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SettingsRead:
    user, _ = await service.update_settings(session, user, payload)
    return await _settings_read(session, user)


@router.put("/channels/slack", response_model=SettingsRead)
async def connect_slack(
    payload: SlackConnect,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    notifiers: dict[str, Notifier] = Depends(get_notifiers),
) -> SettingsRead:
    """Connect (or replace) Slack.

    A test message is sent first, so a mistyped or dead webhook is rejected here instead of
    silently swallowing every future alert.
    """
    key = _require_encryption_key()
    await _deliver_test(notifiers.get("slack"), "slack", payload.webhook_url)
    await service.save_slack_webhook(session, user, payload.webhook_url, key)
    return await _settings_read(session, user)


@router.post("/channels/telegram/link", response_model=TelegramLinkRead)
async def create_telegram_link(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TelegramLinkRead:
    """Issue a one-time link that connects a Telegram chat to this account.

    Opening it and pressing Start makes the bot send our webhook the token, which is what actually
    finishes the connection (see `app/api/v1/endpoints/telegram.py`).
    """
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_BOT_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram isn't available on this server yet.",
        )
    _require_plan_for(user, "telegram")
    token = await telegram_service.create_link_token(
        session, user, settings.TELEGRAM_LINK_TTL_MINUTES
    )
    return TelegramLinkRead(
        url=f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={token}",
        expires_in_minutes=settings.TELEGRAM_LINK_TTL_MINUTES,
    )


@router.patch("/channels/{channel_type}", response_model=SettingsRead)
async def update_channel(
    channel_type: str,
    payload: ChannelUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SettingsRead:
    channel = await _existing_channel(session, user, channel_type)
    await service.set_channel_enabled(session, channel, payload.enabled)
    return await _settings_read(session, user)


@router.delete("/channels/{channel_type}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_channel(
    channel_type: str,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    if channel_type == service.EMAIL_CHANNEL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email can be switched off but not disconnected.",
        )
    channel = await _existing_channel(session, user, channel_type)
    await service.delete_channel(session, channel)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/channels/{channel_type}/test", status_code=status.HTTP_204_NO_CONTENT)
async def send_test_notification(
    channel_type: str,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    notifiers: dict[str, Notifier] = Depends(get_notifiers),
) -> Response:
    """Send a sample notification on one channel, to the same destination real alerts use."""
    _require_plan_for(user, channel_type)
    channel = await service.get_channel(session, user, channel_type)
    if channel is None and channel_type != service.EMAIL_CHANNEL:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not connected")
    try:
        destination = resolve_destination(
            channel_type, user, channel, get_settings().NOTIFY_ENCRYPTION_KEY
        )
    except (EncryptionNotConfigured, UndecryptableSecret) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved connection can't be read, please reconnect.",
        ) from error
    await _deliver_test(notifiers.get(channel_type), channel_type, destination)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
