import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchStats(Base):
    """Daily verdict counters per (watcher, subreddit).

    Rejected candidates are no longer stored row by row, so the analytics dashboard reads its
    totals, pass rate and trend from these counters. `day` is a UTC calendar day.
    """

    __tablename__ = "match_stats"
    __table_args__ = (Index("ix_match_stats_day", "day"),)

    watcher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchers.id", ondelete="CASCADE"), primary_key=True
    )
    subreddit: Mapped[str] = mapped_column(String(100), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    # Candidates the verifier ruled on (confirmed + rejected).
    reviewed: Mapped[int] = mapped_column(Integer, default=0)
    confirmed: Mapped[int] = mapped_column(Integer, default=0)
