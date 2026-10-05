import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationChannel(Base):
    """One delivery channel (email, telegram, ...) a user has configured, and its settings.

    A row always exists for "email" once a user's settings have been read once —
    `get_or_create_email_channel` creates it lazily, the same way `get_or_create_user` creates the
    account row. `config` holds channel-specific data the notification worker will need (e.g. a
    Telegram chat id); it is empty for email since the address lives on `users`.
    """

    __tablename__ = "notification_channels"
    __table_args__ = (
        UniqueConstraint("user_id", "channel_type", name="uq_notification_channels_user_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    channel_type: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # True for email at creation since Clerk already verified the address at signup; a channel that
    # needs its own handshake (Telegram) will start false.
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
