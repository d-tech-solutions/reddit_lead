"""Request and response shapes for the settings API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from app.notifiers.slack import is_valid_webhook_url


class NotificationChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_type: str
    enabled: bool
    verified: bool
    # A connect link was issued and is still waiting for the user to open it (Telegram).
    link_pending: bool = False


class SettingsRead(BaseModel):
    # The Clerk-synced login address, for the UI to show as the override's fallback.
    account_email: str | None
    notification_email: str | None
    channels: list[NotificationChannelRead]


class SettingsUpdate(BaseModel):
    """The settings page always submits its full state, so unlike `WatcherUpdate` there is no
    "leave alone" case to represent — `notification_email` empty/omitted plainly means "use the
    account email."
    """

    notification_email: str | None = None
    email_enabled: bool

    @field_validator("notification_email")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class SlackConnect(BaseModel):
    webhook_url: str

    @field_validator("webhook_url")
    @classmethod
    def _must_be_a_slack_webhook(cls, value: str) -> str:
        stripped = value.strip()
        if not is_valid_webhook_url(stripped):
            raise ValueError("Must be a Slack incoming-webhook URL (https://hooks.slack.com/...)")
        return stripped


class ChannelUpdate(BaseModel):
    enabled: bool


class TelegramLinkRead(BaseModel):
    url: str
    expires_in_minutes: int
