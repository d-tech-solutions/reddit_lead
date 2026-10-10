import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Watcher(Base):
    __tablename__ = "watchers"
    __table_args__ = (
        # Serves the matcher's "watchers covering this subreddit" lookup, which uses the array
        # containment operator (`subreddits @> ARRAY[x]`) — `= ANY(subreddits)` cannot use it.
        Index("ix_watchers_subreddits_gin", "subreddits", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    intent_text: Mapped[str] = mapped_column(Text)
    # The Postgres ARRAY (not sqlalchemy.ARRAY) because only it provides `.contains()` -> `@>`.
    subreddits: Mapped[list[str]] = mapped_column(ARRAY(String(100)))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
