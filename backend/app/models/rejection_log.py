import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RejectionLog(Base):
    """A short-lived record of what the verifier rejected, so a user can see why a post missed.

    Deliberately not linked to any post row (those are deleted once judged) and truncated: it keeps
    just enough to recognise the post and read the verifier's reason. Pruned after
    REJECTION_LOG_RETENTION_DAYS.
    """

    __tablename__ = "rejection_log"
    __table_args__ = (
        Index("ix_rejection_log_watcher_recent", "watcher_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watcher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchers.id", ondelete="CASCADE")
    )
    subreddit: Mapped[str] = mapped_column(String(100))
    reddit_post_id: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    permalink: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
