import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import EMBEDDING_DIMENSIONS
from app.db.base import Base


class Watcher(Base):
    __tablename__ = "watchers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    intent_text: Mapped[str] = mapped_column(Text)
    subreddits: Mapped[list[str]] = mapped_column(ARRAY(String(100)))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # Which side of the transaction the user wants to find: "requesting" (someone asking for
    # work) or "offering" (someone advertising it). Captured as a field rather than inferred from
    # `intent_text`, because embeddings do not reliably encode direction — see
    # docs/PROGRESS.md, 2026-07-30.
    direction: Mapped[str] = mapped_column(String(20), default="requesting")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Vector form of `intent_text`, compared against post embeddings by the matcher. NULL until the
    # embedding worker processes it; re-embedded whenever `intent_text` changes.
    intent_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
