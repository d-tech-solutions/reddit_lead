import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RedditPost(Base):
    """The matcher's work queue: a post lives here only until the LLM has judged it.

    Once judged, the row is deleted in the same transaction that stores the outcome — a confirmed
    post moves to `matched_posts`, a rejected one is simply dropped (its id stays in `seen_posts`
    so it is never fetched again). The table therefore stays as small as the in-flight backlog no
    matter how many posts the pipeline has handled.
    """

    __tablename__ = "reddit_posts"
    __table_args__ = (
        # The claim query: oldest unlocked work first.
        Index("ix_reddit_posts_queue", "fetched_at", "locked_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reddit_post_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    subreddit: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    permalink: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Number of times a worker has claimed this post; a post that keeps failing is dropped once it
    # reaches MATCH_MAX_ATTEMPTS instead of looping forever.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # A worker owns the post until this passes. NULL means free to claim.
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
