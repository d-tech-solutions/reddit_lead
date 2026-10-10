import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Match(Base):
    """A (watcher, post) pair the LLM verifier confirmed.

    Only confirmed matches are stored. Rejections are not kept per row — they are counted in
    `match_stats` and sampled into the short-lived `rejection_log`, so this table grows only with
    real hits.
    """

    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("watcher_id", "matched_post_id", name="uq_matches_pair"),
        # The feed's exact sort key, probed per watcher (see services/matches.py).
        Index("ix_matches_feed", "watcher_id", text("created_at DESC"), text("id DESC")),
        # The unread badge, counted on every feed page load.
        Index("ix_matches_unread", "watcher_id", postgresql_where=text("read_at IS NULL")),
        # The notify worker's sweep: confirmed matches nobody has been told about.
        Index(
            "ix_matches_pending_notification",
            "created_at",
            postgresql_where=text("notified_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watcher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchers.id", ondelete="CASCADE"), index=True
    )
    matched_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matched_posts.id", ondelete="CASCADE"), index=True
    )

    llm_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # When the verifier confirmed the match (rows are only written on confirmation).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Set by the notification worker once the user has been told.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set by the dashboard when the user opens the match.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
