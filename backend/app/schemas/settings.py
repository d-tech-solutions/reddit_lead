"""Request and response shapes for the settings API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class NotificationChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_type: str
    enabled: bool
    verified: bool


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
