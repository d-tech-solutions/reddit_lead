"""Notify worker: tell users about confirmed matches on each channel they have switched on.

Runs as its own Arq consumer (`arq app.workers.notify.WorkerSettings`) so a slow or failing channel
can never hold up matching. The matcher enqueues `notify_match` the moment a match is confirmed; a
cron sweep is the safety net for anything that was never enqueued or only half-delivered — same
two-trigger shape as the rest of the pipeline.

Every (match, channel) pair gets a `notification_deliveries` row, and a `sent` row is never sent
again, so retries, duplicate jobs and the sweep are all safe to overlap.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import UUID

from arq import Retry, cron
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import channel_allowed
from app.core.crypto import (
    EncryptionNotConfigured,
    UndecryptableSecret,
    decrypt_secret,
)
from app.db.session import async_session_factory
from app.models.match import Match
from app.models.notification_channel import NotificationChannel
from app.models.notification_delivery import (
    DELIVERY_FAILED,
    DELIVERY_SENT,
    DELIVERY_SKIPPED,
    DELIVERY_TERMINAL,
    NotificationDelivery,
)
from app.models.reddit_post import RedditPost
from app.models.user import User
from app.models.watcher import Watcher
from app.notifiers import build_notifiers
from app.notifiers.base import (
    Notifier,
    PermanentDeliveryError,
    TemporaryDeliveryError,
    build_message,
)
from app.workers.match import backfill_minutes

logger = logging.getLogger(__name__)

EMAIL = "email"
SLACK = "slack"


def resolve_destination(
    channel_type: str,
    user: User,
    channel: NotificationChannel | None,
    encryption_key: str = "",
) -> str | None:
    """Where this channel should send for this user, or None if nowhere is configured.

    Raises `EncryptionNotConfigured` / `UndecryptableSecret` for a Slack channel whose webhook
    can't be decrypted — the caller decides whether that is worth retrying.
    """
    if channel_type == EMAIL:
        return user.notification_email or user.email
    if channel is None:
        return None
    if channel_type == SLACK:
        token = channel.config.get("webhook_url_encrypted")
        return decrypt_secret(encryption_key, token) if token else None
    return channel.config.get("destination")


async def channels_to_notify(
    session: AsyncSession, user: User, notifiers: dict[str, Notifier]
) -> list[tuple[str, NotificationChannel | None]]:
    """The configured channels that are switched on and verified for this user.

    Email is on by default: its channel row is only created when the user first opens settings, so
    a missing row means "never touched it", not "off".
    """
    result = await session.execute(
        select(NotificationChannel).where(NotificationChannel.user_id == user.id)
    )
    rows = {channel.channel_type: channel for channel in result.scalars()}

    targets: list[tuple[str, NotificationChannel | None]] = []
    for channel_type in notifiers:
        # Re-checked at send time, not only when connecting: a user who downgrades keeps their
        # Telegram row but must stop receiving paid-only alerts.
        if not channel_allowed(user.plan, channel_type):
            continue
        channel = rows.get(channel_type)
        if channel is None:
            if channel_type == EMAIL:
                targets.append((channel_type, None))
            continue
        if channel.enabled and channel.verified:
            targets.append((channel_type, channel))
    return targets


async def claim_delivery(
    session: AsyncSession, match_id: UUID, channel_type: str
) -> NotificationDelivery:
    """Get the delivery row for this pair, creating it on first sight."""
    await session.execute(
        insert(NotificationDelivery)
        .values(match_id=match_id, channel_type=channel_type, status="pending", attempts=0)
        .on_conflict_do_nothing(constraint="uq_notification_deliveries_pair")
    )
    result = await session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.match_id == match_id,
            NotificationDelivery.channel_type == channel_type,
        )
    )
    return result.scalar_one()


async def notify_match(ctx: dict[str, Any], match_id: str) -> int:
    """Arq job: deliver one confirmed match on every enabled channel; returns how many were sent.

    Raises `arq.Retry` when a channel failed temporarily, so Arq re-runs the job after a delay —
    the deliveries already `sent` are skipped on the re-run.
    """
    notifiers: dict[str, Notifier] = ctx["notifiers"]
    settings = ctx["settings"]
    sent = 0
    retry_attempts = 0

    async with async_session_factory() as session:
        match = await session.get(Match, UUID(match_id))
        if match is None or match.llm_verified is not True:
            return 0

        post = await session.get(RedditPost, match.reddit_post_id)
        watcher = await session.get(Watcher, match.watcher_id)
        if post is None or watcher is None or watcher.status != "active":
            return 0
        user = await session.get(User, watcher.user_id)
        if user is None or not user.is_active:
            return 0

        message = build_message(match, post, watcher, settings.FRONTEND_URL)

        for channel_type, channel in await channels_to_notify(session, user, notifiers):
            delivery = await claim_delivery(session, match.id, channel_type)
            if delivery.status in DELIVERY_TERMINAL:
                continue

            try:
                destination = resolve_destination(
                    channel_type, user, channel, settings.NOTIFY_ENCRYPTION_KEY
                )
            except EncryptionNotConfigured:
                # Our misconfiguration, not the user's: leave the delivery pending so the sweep
                # sends it once the key is set, rather than recording a failure.
                logger.error("notify: NOTIFY_ENCRYPTION_KEY missing, cannot send %s", channel_type)
                continue
            except UndecryptableSecret as error:
                delivery.status = DELIVERY_FAILED
                delivery.last_error = str(error)
                if channel is not None:
                    channel.verified = False
                await session.commit()
                continue
            if not destination:
                delivery.status = DELIVERY_SKIPPED
                delivery.last_error = "no destination configured"
                await session.commit()
                continue

            delivery.attempts += 1
            try:
                await notifiers[channel_type].send(destination, message)
            except TemporaryDeliveryError as error:
                delivery.last_error = str(error)
                if delivery.attempts >= settings.NOTIFY_MAX_ATTEMPTS:
                    delivery.status = DELIVERY_FAILED
                else:
                    retry_attempts = max(retry_attempts, delivery.attempts)
                logger.warning(
                    "notify: match=%s channel=%s temporary failure (attempt %d): %s",
                    match.id, channel_type, delivery.attempts, error,
                )
            except PermanentDeliveryError as error:
                delivery.status = DELIVERY_FAILED
                delivery.last_error = str(error)
                # A dead webhook or blocked bot stays dead; flag the channel so the UI can ask the
                # user to reconnect. Email has no such handshake, so it is left alone.
                if channel is not None and channel_type != EMAIL:
                    channel.verified = False
                logger.warning(
                    "notify: match=%s channel=%s permanent failure: %s",
                    match.id, channel_type, error,
                )
            else:
                delivery.status = DELIVERY_SENT
                delivery.sent_at = datetime.now(UTC)
                delivery.last_error = None
                match.notified_at = match.notified_at or delivery.sent_at
                sent += 1
            await session.commit()

    if retry_attempts:
        # Back off 30s, 60s, 90s... between attempts.
        raise Retry(defer=30 * retry_attempts)
    return sent


async def fetch_pending_match_ids(session: AsyncSession, window_hours: int, limit: int) -> list[UUID]:
    """Confirmed, recent matches nobody has been told about and no delivery has given up on."""
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    settled = select(NotificationDelivery.match_id).where(
        NotificationDelivery.match_id == Match.id,
        NotificationDelivery.status.in_((DELIVERY_FAILED, DELIVERY_SKIPPED)),
    )
    result = await session.execute(
        select(Match.id)
        .where(
            Match.llm_verified.is_(True),
            Match.notified_at.is_(None),
            Match.verified_at >= cutoff,
            ~settled.exists(),
        )
        .order_by(Match.verified_at)
        .limit(limit)
    )
    return list(result.scalars())


async def backfill(ctx: dict[str, Any]) -> int:
    """Arq cron job: deliver matches whose notify job never ran or never finished."""
    settings = ctx["settings"]
    async with async_session_factory() as session:
        match_ids = await fetch_pending_match_ids(
            session, settings.NOTIFY_BACKFILL_WINDOW_HOURS, settings.NOTIFY_BACKFILL_LIMIT
        )

    handled = 0
    for match_id in match_ids:
        try:
            handled += await notify_match(ctx, str(match_id))
        except Retry:
            # Left pending; the next sweep tries again.
            continue
        except Exception:
            logger.exception("notify backfill: match=%s failed", match_id)

    if handled:
        logger.info("notify backfill: sent=%d", handled)
    return handled


async def startup(ctx: dict[str, Any]) -> None:
    """Arq startup hook: build the notifiers once per worker process."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ctx["settings"] = settings
    ctx["notifiers"] = build_notifiers(settings)
    logger.info("notifier starting: channels=%s", sorted(ctx["notifiers"]) or "none configured")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Arq shutdown hook: close each notifier's HTTP client."""
    for notifier in ctx.get("notifiers", {}).values():
        await notifier.close()


_settings = get_settings()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [notify_match]
    cron_jobs: ClassVar[list[Any]] = [
        cron(
            backfill,
            minute=backfill_minutes(_settings.NOTIFY_BACKFILL_INTERVAL_MINUTES),
            run_at_startup=True,
        )
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.REDIS_URL)
    # Retries are driven by `arq.Retry` against NOTIFY_MAX_ATTEMPTS; this is only the upper bound.
    max_tries = _settings.NOTIFY_MAX_ATTEMPTS
