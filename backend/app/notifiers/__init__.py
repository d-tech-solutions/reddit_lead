"""Notification channels. One module per channel, all behind the `Notifier` protocol in `base`."""

from __future__ import annotations

from app.core.config import Settings
from app.notifiers.base import Notifier
from app.notifiers.email import EmailNotifier
from app.notifiers.slack import SlackNotifier
from app.notifiers.telegram import TelegramNotifier


def build_notifiers(settings: Settings) -> dict[str, Notifier]:
    """Build the notifier for every channel that is configured, keyed by channel type.

    A channel with no credentials is left out rather than failing: the worker then ignores it, and
    its matches stay un-notified for the backfill sweep instead of being marked failed.
    """
    notifiers: dict[str, Notifier] = {}
    if settings.RESEND_API_KEY:
        notifiers["email"] = EmailNotifier(settings.RESEND_API_KEY, settings.NOTIFY_FROM_EMAIL)
    # Slack needs no server-side credential: each user brings their own webhook.
    notifiers["slack"] = SlackNotifier()
    if settings.TELEGRAM_BOT_TOKEN:
        notifiers["telegram"] = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN)
    return notifiers
