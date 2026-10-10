import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchedPost(Base):
    """A Reddit post that at least one watcher's intent confirmed.

    Holds the full post content so the feed, notifications and the admin post view never need the
    original `reddit_posts` row (which is deleted once the post is judged). One row per Reddit
    post, shared by every watcher it matched; rows are removed once no match references them.
    """

    __tablename__ = "matched_posts"
    __table_args__ = (
        Index("ix_matched_posts_feed", text("fetched_at DESC"), text("id DESC")),
        Index(
            "ix_matched_posts_subreddit_feed", "subreddit", text("fetched_at DESC"), text("id DESC")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reddit_post_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    subreddit: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    permalink: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
