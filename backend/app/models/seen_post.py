from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SeenPost(Base):
    """A Reddit post id the ingestion worker has already handled.

    Deleting a judged post from `reddit_posts` would otherwise let the next poll re-ingest and
    re-judge it. This narrow table is the dedup memory; it only needs to outlive the ingest age
    window, so old rows are pruned (SEEN_POSTS_RETENTION_DAYS).
    """

    __tablename__ = "seen_posts"

    reddit_post_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
