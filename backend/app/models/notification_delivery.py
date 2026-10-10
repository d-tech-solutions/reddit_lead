import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DELIVERY_PENDING = "pending"
DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"
DELIVERY_SKIPPED = "skipped"
# States the notify worker never revisits.
DELIVERY_TERMINAL = (DELIVERY_SENT, DELIVERY_FAILED, DELIVERY_SKIPPED)


class NotificationDelivery(Base):
    """One attempt-trail for telling one user about one match on one channel.

    `matches.notified_at` can only say "somebody was told"; this table says which channel, whether
    it worked, and why not. The unique (match, channel) pair is what makes a retried or
    double-enqueued job harmless — a `sent` row is never sent again.
    """

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("match_id", "channel_type", name="uq_notification_deliveries_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), index=True
    )
    channel_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=DELIVERY_PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
