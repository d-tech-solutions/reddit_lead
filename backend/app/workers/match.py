"""Matcher worker: ask an LLM whether each active, subscribed watcher matches a new post.

Runs as an Arq consumer (`arq app.workers.match.WorkerSettings`), triggered by the ingestion
worker the moment a post is inserted, with a backfill sweep as the safety net — same two-trigger
shape the pipeline has used throughout (docs/ingestion-worker/README.md §3).

One stage per post: find every active watcher whose subreddit list covers this post (a plain DB
query, no vector search), then ask the verifier for one verdict per watcher in a single batched
call (chunked if there are many candidates). Every candidate is written to `matches` whether it
passes or fails, so the rejected rows stay a record of what the verifier saw and decided.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

from arq import cron
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MATCH_QUEUE, NOTIFY_QUEUE, get_settings
from app.db.session import async_session_factory
from app.models.match import Match
from app.models.reddit_post import RedditPost
from app.models.watcher import Watcher
from app.workers.verifier import IntentVerifier, Verdict, build_verifier

logger = logging.getLogger(__name__)


async def fetch_candidate_watchers(session: AsyncSession, subreddit: str) -> list[Watcher]:
    """Load active watchers whose subreddit list covers this post.

    Filtering in SQL keeps the candidate set small before anything is sent to the LLM.
    """
    result = await session.execute(
        select(Watcher).where(
            Watcher.status == "active",
            Watcher.subreddits.any(subreddit),
        )
    )
    return list(result.scalars())


def chunk_watchers(watchers: list[Watcher], batch_size: int) -> list[list[Watcher]]:
    """Split candidates into fixed-size groups so one busy subreddit isn't one oversized call."""
    return [watchers[index : index + batch_size] for index in range(0, len(watchers), batch_size)]


async def store_placeholder_matches(
    session: AsyncSession, post_id: UUID, watcher_ids: list[UUID]
) -> list[UUID]:
    """Write one placeholder row per (watcher, post), skipping pairs already recorded.

    `llm_verified` stays NULL until a verdict is applied — a job that dies mid-batch leaves a clean
    trail the backfill sweep already knows how to find.
    """
    if not watcher_ids:
        return []

    rows = [{"watcher_id": watcher_id, "reddit_post_id": post_id} for watcher_id in watcher_ids]
    statement = (
        insert(Match)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_matches_pair")
        .returning(Match.id)
    )
    result = await session.execute(statement)
    inserted = list(result.scalars().all())
    await session.commit()
    return inserted


async def apply_verdicts(session: AsyncSession, post_id: UUID, verdicts: list[Verdict]) -> int:
    """Write a batch of verdicts onto their match rows, one commit for the whole batch.

    Skips a verdict whose row is missing or already judged, so a retried batch is idempotent.
    """
    if not verdicts:
        return 0

    confirmed = 0
    now = datetime.now(UTC)
    for verdict in verdicts:
        result = await session.execute(
            select(Match).where(
                Match.reddit_post_id == post_id,
                Match.watcher_id == verdict.watcher_id,
                Match.llm_verified.is_(None),
            )
        )
        match = result.scalar_one_or_none()
        if match is None:
            continue

        match.llm_verified = verdict.matches
        match.llm_reason = verdict.reason
        match.llm_model = verdict.model
        match.verified_at = now
        if verdict.matches:
            confirmed += 1

    await session.commit()
    return confirmed


async def _verify_and_apply(
    session: AsyncSession,
    verifier: IntentVerifier,
    post: RedditPost,
    watchers: list[Watcher],
) -> int:
    """Ask the verifier about one chunk of candidates and apply the verdicts.

    A failed chunk is logged and left NULL — the backfill sweep retries it — rather than failing
    the whole post.
    """
    candidates = [(watcher.id, watcher.intent_text) for watcher in watchers]
    try:
        verdicts = await verifier.verify_batch(post.title, post.body or "", candidates)
    except Exception:
        logger.exception(
            "verify: post=%s batch of %d watchers failed, left for backfill",
            post.reddit_post_id,
            len(watchers),
        )
        return 0

    confirmed = await apply_verdicts(session, post.id, verdicts)
    logger.info(
        "verify: post=%s watchers=%d verdicts=%d confirmed=%d",
        post.reddit_post_id,
        len(watchers),
        len(verdicts),
        confirmed,
    )
    return confirmed


async def enqueue_notifications(
    redis: ArqRedis | None, session: AsyncSession, post_id: UUID
) -> None:
    """Hand this post's confirmed, un-notified matches to the notify worker.

    Best-effort: a failed enqueue is logged and left to the notify worker's own backfill sweep,
    never allowed to fail the matching job.
    """
    if redis is None:
        return
    result = await session.execute(
        select(Match.id).where(
            Match.reddit_post_id == post_id,
            Match.llm_verified.is_(True),
            Match.notified_at.is_(None),
        )
    )
    for match_id in result.scalars():
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


async def match_post(ctx: dict[str, Any], post_id: str) -> int:
    """Arq job: judge one post against every active watcher subscribed to its subreddit.

    Enqueued by the ingestion worker the moment a post is inserted.
    """
    verifier: IntentVerifier = ctx["verifier"]
    settings = ctx["settings"]

    async with async_session_factory() as session:
        post = await session.get(RedditPost, UUID(post_id))
        if post is None:
            logger.warning("match_post: post %s no longer exists", post_id)
            return 0

        watchers = await fetch_candidate_watchers(session, post.subreddit)
        if not watchers:
            return 0

        await store_placeholder_matches(session, post.id, [watcher.id for watcher in watchers])

        confirmed = 0
        for chunk in chunk_watchers(watchers, settings.MATCH_BATCH_SIZE):
            confirmed += await _verify_and_apply(session, verifier, post, chunk)

        if confirmed:
            await enqueue_notifications(ctx.get("redis"), session, post.id)

    return confirmed


async def fetch_unverified_by_post(session: AsyncSession, limit: int) -> dict[UUID, list[UUID]]:
    """Load unverified candidate rows, oldest first, grouped by post for one batched call each."""
    result = await session.execute(
        select(Match.reddit_post_id, Match.watcher_id)
        .where(Match.llm_verified.is_(None))
        .order_by(Match.created_at)
        .limit(limit)
    )
    grouped: dict[UUID, list[UUID]] = {}
    for post_id, watcher_id in result.all():
        grouped.setdefault(post_id, []).append(watcher_id)
    return grouped


async def fetch_unmatched_posts(session: AsyncSession, limit: int) -> list[RedditPost]:
    """Load posts with no `matches` row at all — ones a `match_post` job never ran for (enqueue
    failure, or a job that exhausted its retries).

    A post in a subreddit nobody watches produces no candidates and so is re-checked every sweep;
    that's cheap and also correct, since a watcher added later should still pick it up.
    """
    has_matches = select(Match.reddit_post_id).where(Match.reddit_post_id == RedditPost.id)
    result = await session.execute(
        select(RedditPost)
        .where(~has_matches.exists())
        .order_by(RedditPost.fetched_at)
        .limit(limit)
    )
    return list(result.scalars())


async def backfill(ctx: dict[str, Any]) -> int:
    """Arq cron job: catch candidates whose verification never completed, and posts no job ever
    ran for."""
    verifier: IntentVerifier = ctx["verifier"]
    settings = ctx["settings"]

    handled = 0
    async with async_session_factory() as session:
        # Unjudged candidates first: already-paid-for placeholder rows waiting on a verdict.
        unverified = await fetch_unverified_by_post(session, settings.MATCH_BACKFILL_LIMIT)
        for post_id, watcher_ids in unverified.items():
            post = await session.get(RedditPost, post_id)
            if post is None:
                continue
            watchers = [
                watcher
                for watcher_id in watcher_ids
                if (watcher := await session.get(Watcher, watcher_id)) is not None
            ]
            if not watchers:
                continue
            for chunk in chunk_watchers(watchers, settings.MATCH_BATCH_SIZE):
                await _verify_and_apply(session, verifier, post, chunk)
                handled += len(chunk)

        for post in await fetch_unmatched_posts(session, settings.MATCH_BACKFILL_LIMIT):
            watchers = await fetch_candidate_watchers(session, post.subreddit)
            if not watchers:
                continue
            await store_placeholder_matches(session, post.id, [w.id for w in watchers])
            for chunk in chunk_watchers(watchers, settings.MATCH_BATCH_SIZE):
                await _verify_and_apply(session, verifier, post, chunk)
                handled += len(chunk)

    if handled:
        logger.info("match backfill: handled=%d", handled)
    return handled


def backfill_minutes(interval_minutes: int) -> set[int]:
    """Turn a "run every N minutes" setting into the minute set Arq's cron helper expects."""
    interval = max(1, min(60, interval_minutes))
    while 60 % interval != 0:
        interval -= 1
    return {minute for minute in range(60) if minute % interval == 0}


async def startup(ctx: dict[str, Any]) -> None:
    """Arq startup hook: build the verifier once per worker process rather than per job."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ctx["settings"] = settings
    ctx["verifier"] = build_verifier(settings.OPENAI_API_KEY, settings.VERIFIER_MODEL)

    logger.info(
        "matcher starting: verifier=%s batch_size=%d backfill_every=%dm",
        settings.VERIFIER_MODEL,
        settings.MATCH_BATCH_SIZE,
        settings.MATCH_BACKFILL_INTERVAL_MINUTES,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    """Arq shutdown hook: close the verifier's HTTP client so the process exits cleanly."""
    verifier = ctx.get("verifier")
    if verifier is not None:
        await verifier.close()


_settings = get_settings()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [match_post]
    cron_jobs: ClassVar[list[Any]] = [
        cron(
            backfill,
            minute=backfill_minutes(_settings.MATCH_BACKFILL_INTERVAL_MINUTES),
            run_at_startup=True,
        )
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.REDIS_URL)
    queue_name = MATCH_QUEUE
    # Three attempts, then leave it to the backfill sweep.
    max_tries = 3
