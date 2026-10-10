"""Aggregate queries behind the analytics dashboard.

Same ownership rule as `matches.py`: every query joins `matches -> watchers` and filters on
`watchers.user_id`, because `matches` has no user column of its own.

"Confirmed" is `llm_verified IS TRUE`, "rejected" is `IS FALSE`, and NULL ("verifier has not run")
is kept out of every rate — counting it as a rejection would make a busy queue look like bad matching.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.reddit_post import RedditPost
from app.models.watcher import Watcher
from app.schemas.analytics import (
    Analytics,
    DailyCount,
    SubredditStat,
    VerdictTotals,
    WatcherStat,
)

TOP_SUBREDDIT_LIMIT = 10


def _pass_rate(confirmed: int, reviewed: int) -> float | None:
    return confirmed / reviewed if reviewed else None


def _confirmed_count():
    return func.coalesce(func.sum(cast(Match.llm_verified.is_(True), Integer)), 0)


def _reviewed_count():
    return func.coalesce(func.sum(cast(Match.llm_verified.is_not(None), Integer)), 0)


async def build_analytics(session: AsyncSession, user_id: uuid.UUID, days: int) -> Analytics:
    """Compute the whole dashboard for one user over the trailing `days` days."""
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    in_scope = (Watcher.user_id == user_id, Match.created_at >= since)

    # Verdict totals.
    row = (
        await session.execute(
            select(
                _confirmed_count(),
                func.coalesce(func.sum(cast(Match.llm_verified.is_(False), Integer)), 0),
                func.coalesce(func.sum(cast(Match.llm_verified.is_(None), Integer)), 0),
            )
            .select_from(Match)
            .join(Watcher, Match.watcher_id == Watcher.id)
            .where(*in_scope)
        )
    ).one()
    confirmed, rejected, pending = int(row[0]), int(row[1]), int(row[2])
    totals = VerdictTotals(
        confirmed=confirmed,
        rejected=rejected,
        pending=pending,
        pass_rate=_pass_rate(confirmed, confirmed + rejected),
    )

    # Confirmed matches per UTC day, zero-filled so the chart has no gaps to interpolate over.
    day_col = func.date(func.timezone("UTC", Match.created_at))
    by_day = {
        day: int(count)
        for day, count in (
            await session.execute(
                select(day_col, func.count())
                .select_from(Match)
                .join(Watcher, Match.watcher_id == Watcher.id)
                .where(*in_scope, Match.llm_verified.is_(True))
                .group_by(day_col)
            )
        ).all()
    }
    today = now.date()
    daily = [
        DailyCount(day=d, confirmed=by_day.get(d, 0))
        for d in (today - timedelta(days=offset) for offset in range(days - 1, -1, -1))
    ]

    # Subreddits that produced the most confirmed matches.
    subreddit_rows = (
        await session.execute(
            select(RedditPost.subreddit, _confirmed_count(), _reviewed_count())
            .select_from(Match)
            .join(Watcher, Match.watcher_id == Watcher.id)
            .join(RedditPost, Match.reddit_post_id == RedditPost.id)
            .where(*in_scope)
            .group_by(RedditPost.subreddit)
            .having(_confirmed_count() > 0)
            .order_by(_confirmed_count().desc(), RedditPost.subreddit)
            .limit(TOP_SUBREDDIT_LIMIT)
        )
    ).all()
    top_subreddits = [
        SubredditStat(
            subreddit=name,
            confirmed=int(c),
            reviewed=int(r),
            pass_rate=_pass_rate(int(c), int(r)),
        )
        for name, c, r in subreddit_rows
    ]

    # Every watcher the user owns, including ones with no matches in the window: a watcher that
    # never fires is exactly what this table should surface. The window lives in the join
    # condition, not WHERE, so those watchers survive the outer join.
    last_match = func.max(case((Match.llm_verified.is_(True), Match.created_at)))
    watcher_rows = (
        await session.execute(
            select(Watcher, _confirmed_count(), _reviewed_count(), last_match)
            .outerjoin(Match, (Match.watcher_id == Watcher.id) & (Match.created_at >= since))
            .where(Watcher.user_id == user_id)
            .group_by(Watcher.id)
            .order_by(_confirmed_count().desc(), Watcher.name)
        )
    ).all()
    watchers = [
        WatcherStat(
            id=w.id,
            name=w.name,
            status=w.status,
            confirmed=int(c),
            reviewed=int(r),
            pass_rate=_pass_rate(int(c), int(r)),
            last_match_at=last,
        )
        for w, c, r, last in watcher_rows
    ]

    return Analytics(
        days=days,
        totals=totals,
        daily=daily,
        top_subreddits=top_subreddits,
        watchers=watchers,
    )
