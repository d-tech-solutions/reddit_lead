"""Response shapes for the analytics dashboard."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

# Window choices the UI offers. The endpoint clamps to this range rather than rejecting, so a
# hand-edited `?days=` still renders something sensible.
MIN_DAYS = 1
MAX_DAYS = 365
DEFAULT_DAYS = 30


class VerdictTotals(BaseModel):
    """What the LLM verifier decided about candidates in the window.

    This is the verifier's verdict, not the user's — there is no user feedback to count yet.
    `pass_rate` is null when nothing has been decided, so the UI can show a dash and not "0%".
    """

    confirmed: int
    rejected: int
    pass_rate: float | None


class DailyCount(BaseModel):
    day: date
    confirmed: int


class SubredditStat(BaseModel):
    subreddit: str
    confirmed: int
    # Confirmed + rejected: the candidates the verifier actually ruled on.
    reviewed: int
    pass_rate: float | None


class WatcherStat(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    confirmed: int
    reviewed: int
    pass_rate: float | None
    last_match_at: datetime | None


class RejectionRead(BaseModel):
    """One recently rejected candidate: enough to recognise the post and read the verifier's reason.

    Comes from a short-lived sample (`rejection_log`), not a permanent record.
    """

    watcher_id: uuid.UUID
    watcher_name: str
    subreddit: str
    title: str
    permalink: str
    reason: str
    rejected_at: datetime


class Analytics(BaseModel):
    days: int
    totals: VerdictTotals
    # One entry per calendar day in the window (UTC), oldest first, zero-filled.
    daily: list[DailyCount]
    top_subreddits: list[SubredditStat]
    watchers: list[WatcherStat]
    # Newest first, capped; empty once the sample has aged out.
    recent_rejections: list[RejectionRead]
