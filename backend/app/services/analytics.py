"""Aggregate queries behind the analytics dashboard.

Same ownership rule as `matches.py`: every query joins to `watchers` and filters on
`watchers.user_id`, because the stats tables have no user column of their own.

Rejected candidates are not stored per row, so totals, pass rate and the trend come from the daily
`match_stats` counters (reviewed = confirmed + rejected). The "recently rejected" list comes from
`rejection_log`, a short-lived sample that carries the verifier's reasons.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.match_stats import MatchStats
from app.models.rejection_log import RejectionLog
from app.models.watcher import Watcher
from app.schemas.analytics import (
    Analytics,
    DailyCount,
    RejectionRead,
    SubredditStat,
    VerdictTotals,
    WatcherStat,
)

TOP_SUBREDDIT_LIMIT = 10
RECENT_REJECTION_LIMIT = 20


def _pass_rate(confirmed: int, reviewed: int) -> float | None:
    return confirmed / reviewed if reviewed else None


def _confirmed_sum():
    return func.coalesce(func.sum(MatchStats.confirmed), 0)


def _reviewed_sum():
    return func.coalesce(func.sum(MatchStats.reviewed), 0)


async def build_analytics(session: AsyncSession, user_id: uuid.UUID, days: int) -> Analytics:
    """Compute the whole dashboard for one user over the trailing `days` days (UTC, inclusive)."""
    now = datetime.now(UTC)
    today = now.date()
    first_day = today - timedelta(days=days - 1)
    in_scope = (Watcher.user_id == user_id, MatchStats.day >= first_day)

    # Verdict totals.
    row = (
        await session.execute(
            select(_confirmed_sum(), _reviewed_sum())
            .select_from(MatchStats)
            .join(Watcher, MatchStats.watcher_id == Watcher.id)
            .where(*in_scope)
        )
    ).one()
    confirmed, reviewed = int(row[0]), int(row[1])
    totals = VerdictTotals(
        confirmed=confirmed,
        rejected=reviewed - confirmed,
        pass_rate=_pass_rate(confirmed, reviewed),
    )

    # Confirmed matches per UTC day, zero-filled so the chart has no gaps to interpolate over.
    by_day = {
        day: int(count)
        for day, count in (
            await session.execute(
                select(MatchStats.day, _confirmed_sum())
                .select_from(MatchStats)
                .join(Watcher, MatchStats.watcher_id == Watcher.id)
                .where(*in_scope)
                .group_by(MatchStats.day)
            )
        ).all()
    }
    daily = [
        DailyCount(day=d, confirmed=by_day.get(d, 0))
        for d in (today - timedelta(days=offset) for offset in range(days - 1, -1, -1))
    ]

    # Subreddits that produced the most confirmed matches.
    subreddit_rows = (
        await session.execute(
            select(MatchStats.subreddit, _confirmed_sum(), _reviewed_sum())
            .select_from(MatchStats)
            .join(Watcher, MatchStats.watcher_id == Watcher.id)
            .where(*in_scope)
            .group_by(MatchStats.subreddit)
            .having(_confirmed_sum() > 0)
            .order_by(_confirmed_sum().desc(), MatchStats.subreddit)
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

    # Every watcher the user owns, including ones with no activity in the window: a watcher that
    # never fires is exactly what this table should surface. The window lives in the join
    # condition, not WHERE, so those watchers survive the outer join.
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=UTC)
    last_match = (
        select(func.max(Match.created_at))
        .where(Match.watcher_id == Watcher.id, Match.created_at >= since)
        .scalar_subquery()
    )
    watcher_rows = (
        await session.execute(
            select(Watcher, _confirmed_sum(), _reviewed_sum(), last_match)
            .outerjoin(
                MatchStats,
                (MatchStats.watcher_id == Watcher.id) & (MatchStats.day >= first_day),
            )
            .where(Watcher.user_id == user_id)
            .group_by(Watcher.id)
            .order_by(_confirmed_sum().desc(), Watcher.name)
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

    rejection_rows = (
        await session.execute(
            select(RejectionLog, Watcher.name)
            .join(Watcher, RejectionLog.watcher_id == Watcher.id)
            .where(Watcher.user_id == user_id)
            .order_by(RejectionLog.created_at.desc(), RejectionLog.id.desc())
            .limit(RECENT_REJECTION_LIMIT)
        )
    ).all()
    recent_rejections = [
        RejectionRead(
            watcher_id=entry.watcher_id,
            watcher_name=watcher_name,
            subreddit=entry.subreddit,
            title=entry.title,
            permalink=entry.permalink,
            reason=entry.reason,
            rejected_at=entry.created_at,
        )
        for entry, watcher_name in rejection_rows
    ]

    return Analytics(
        days=days,
        totals=totals,
        daily=daily,
        top_subreddits=top_subreddits,
        watchers=watchers,
        recent_rejections=recent_rejections,
    )
