"""Persisting what the verifier decided, shared by the queue matcher and the new-watcher catch-up.

Both paths end the same way: a confirmed (watcher, post) pair becomes a `matches` row pointing at a
`matched_posts` row, a rejected pair is counted and sampled into `rejection_log`, and every ruling
bumps the day's `match_stats` counters. Keeping that in one function means the two paths cannot
drift apart.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from arq.connections import ArqRedis
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import NOTIFY_QUEUE
from app.models.match import Match
from app.models.match_stats import MatchStats
from app.models.matched_post import MatchedPost
from app.models.reddit_post import RedditPost
from app.models.rejection_log import RejectionLog

logger = logging.getLogger(__name__)

# Matches the column widths on `rejection_log`.
TITLE_CHARS = 300
REASON_CHARS = 500


@dataclass(frozen=True)
class Outcome:
    """One verdict about one (watcher, post) pair.

    `post` is a plain dict (reddit_post_id, subreddit, title, body, author, permalink, posted_at,
    fetched_at) so it can come from a queue row or straight from the Reddit source.
    """

    watcher_id: UUID
    post: dict[str, Any]
    matches: bool
    reason: str
    model: str


def post_to_dict(post: RedditPost) -> dict[str, Any]:
    """The fields `matched_posts` stores, read off a queue row."""
    return {
        "reddit_post_id": post.reddit_post_id,
        "subreddit": post.subreddit,
        "title": post.title,
        "body": post.body or "",
        "author": post.author,
        "permalink": post.permalink,
        "posted_at": post.posted_at,
        "fetched_at": post.fetched_at,
    }


async def store_outcomes(session: AsyncSession, outcomes: list[Outcome]) -> list[UUID]:
    """Write a batch of verdicts; returns the ids of the `matches` rows newly created.

    Runs entirely in the caller's transaction and does not commit, so the caller can delete the
    queue row in the same transaction and a crash can never lose a match or leave a half-move.
    Idempotent: a repeated (watcher, post) pair is skipped by the unique constraint.
    """
    # The model should return each candidate once; if it repeats one, the multi-row upserts below
    # would fail on their own conflict, so keep the first verdict per pair.
    unique: dict[tuple[UUID, str], Outcome] = {}
    for outcome in outcomes:
        unique.setdefault((outcome.watcher_id, outcome.post["reddit_post_id"]), outcome)
    outcomes = list(unique.values())
    if not outcomes:
        return []

    now = datetime.now(UTC)
    new_match_ids: list[UUID] = []

    confirmed = [outcome for outcome in outcomes if outcome.matches]
    if confirmed:
        posts_by_reddit_id = {o.post["reddit_post_id"]: o.post for o in confirmed}
        post_rows = [
            {
                "reddit_post_id": post["reddit_post_id"],
                "subreddit": post["subreddit"],
                "title": post["title"],
                "body": post.get("body") or "",
                "author": post.get("author"),
                "permalink": post["permalink"],
                "posted_at": post.get("posted_at"),
                "fetched_at": post.get("fetched_at") or now,
            }
            for post in posts_by_reddit_id.values()
        ]
        post_statement = insert(MatchedPost).values(post_rows)
        # A no-op update so RETURNING yields the id whether the row is new or already stored by
        # another watcher's match.
        post_statement = post_statement.on_conflict_do_update(
            index_elements=["reddit_post_id"],
            set_={"subreddit": post_statement.excluded.subreddit},
        ).returning(MatchedPost.id, MatchedPost.reddit_post_id)
        result = await session.execute(post_statement)
        matched_post_ids = {reddit_id: row_id for row_id, reddit_id in result.all()}

        match_rows = [
            {
                "watcher_id": outcome.watcher_id,
                "matched_post_id": matched_post_ids[outcome.post["reddit_post_id"]],
                "llm_reason": outcome.reason[:REASON_CHARS],
                "llm_model": outcome.model,
            }
            for outcome in confirmed
        ]
        match_result = await session.execute(
            insert(Match)
            .values(match_rows)
            .on_conflict_do_nothing(constraint="uq_matches_pair")
            .returning(Match.id)
        )
        new_match_ids = list(match_result.scalars().all())

    rejected = [outcome for outcome in outcomes if not outcome.matches]
    if rejected:
        await session.execute(
            insert(RejectionLog).values(
                [
                    {
                        "watcher_id": outcome.watcher_id,
                        "subreddit": outcome.post["subreddit"],
                        "reddit_post_id": outcome.post["reddit_post_id"],
                        "title": outcome.post["title"][:TITLE_CHARS],
                        "permalink": outcome.post["permalink"],
                        "reason": outcome.reason[:REASON_CHARS],
                        "model": outcome.model,
                    }
                    for outcome in rejected
                ]
            )
        )

    await _bump_stats(session, outcomes, now.date())
    return new_match_ids


async def _bump_stats(session: AsyncSession, outcomes: list[Outcome], day: Any) -> None:
    """Add this batch to the (watcher, subreddit, day) counters in one upsert."""
    counts: dict[tuple[UUID, str], list[int]] = {}
    for outcome in outcomes:
        key = (outcome.watcher_id, outcome.post["subreddit"])
        reviewed_confirmed = counts.setdefault(key, [0, 0])
        reviewed_confirmed[0] += 1
        if outcome.matches:
            reviewed_confirmed[1] += 1

    statement = insert(MatchStats).values(
        [
            {
                "watcher_id": watcher_id,
                "subreddit": subreddit,
                "day": day,
                "reviewed": reviewed,
                "confirmed": confirmed,
            }
            for (watcher_id, subreddit), (reviewed, confirmed) in counts.items()
        ]
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["watcher_id", "subreddit", "day"],
            set_={
                "reviewed": MatchStats.reviewed + statement.excluded.reviewed,
                "confirmed": MatchStats.confirmed + statement.excluded.confirmed,
            },
        )
    )


async def enqueue_notifications(redis: ArqRedis | None, match_ids: list[UUID]) -> None:
    """Hand newly confirmed matches to the notify worker.

    Best-effort: a failed enqueue is logged and left to the notify worker's own sweep, never
    allowed to fail the matching job.
    """
    if redis is None:
        return
    for match_id in match_ids:
        try:
            # A job id derived from the match id makes a duplicate enqueue a no-op.
            await redis.enqueue_job(
                "notify_match",
                str(match_id),
                _job_id=f"notify_match:{match_id}",
                _queue_name=NOTIFY_QUEUE,
            )
        except Exception:
            logger.exception("match: failed enqueueing notify job for match %s", match_id)
