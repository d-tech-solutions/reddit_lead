import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Match(Base):
    """A (watcher, post) pair the matcher considered, and what the verifier decided about it.

    Rows are written for *every* candidate that clears the vector gate, not only confirmed
    matches — the rejected ones are the labelled data that eventually calibrates the gate
    (see docs/PROGRESS.md, 2026-07-30). Read `llm_verified` to distinguish: NULL means the
    verifier has not run yet, False means it ran and said no.
    """

    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("watcher_id", "reddit_post_id", name="uq_matches_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watcher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchers.id", ondelete="CASCADE"), index=True
    )
    reddit_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reddit_posts.id", ondelete="CASCADE"), index=True
    )

    # Raw cosine similarity between the watcher's intent vector and the post's vector.
    similarity: Mapped[float] = mapped_column(Float)
    # Projection of the post onto the global request/offer axis. Positive = reads like an offer,
    # negative = reads like a request. See app/workers/direction.py.
    direction_score: Mapped[float] = mapped_column(Float)
    # similarity minus the direction penalty — what the top-K gate actually ranked on.
    adjusted_score: Mapped[float] = mapped_column(Float)

    # NULL until the verifier runs; False is a real "no", not a missing value.
    llm_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    llm_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set by the notification worker once the user has been told. Nothing writes it yet.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set by the dashboard when the user opens the match. Nothing writes it yet.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
