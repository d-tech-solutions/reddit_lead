"""Matcher worker: judge each queued post against the watchers that follow its subreddit.

Runs as an Arq consumer (`arq app.workers.match.WorkerSettings`), triggered by the ingestion
worker the moment a post is queued, with a backfill sweep as the safety net.

`reddit_posts` is the work queue. A worker *claims* a post (a lease, `FOR UPDATE SKIP LOCKED`, so
several workers never take the same one), asks the verifier for one verdict per candidate watcher,
then in ONE transaction stores the outcome (`matched_posts` + `matches` for confirmations, counters
and a short rejection sample for the rest) and deletes the queue row. The LLM calls happen with no
transaction open. A post that cannot be judged stays queued with a backoff and is dropped after
MATCH_MAX_ATTEMPTS claims.

This worker also runs the new-watcher catch-up (`catchup_watcher`) and the retention cron.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import UUID

from arq import cron
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MATCH_QUEUE, Settings, get_settings
from app.db.session import async_session_factory
from app.models.reddit_post import RedditPost
from app.models.watcher import Watcher
from app.services.retention import run_retention
from app.workers.outcomes import (
    Outcome,
    enqueue_notifications,
    post_to_dict,
    store_outcomes,
)
from app.workers.reddit_source import PostSource, build_source
from app.workers.verifier import IntentVerifier, Verdict, build_verifier

logger = logging.getLogger(__name__)

# (watcher id, intent text) — all the matcher needs of a watcher, without holding ORM rows across
# the commits and LLM calls that follow.
Candidate = tuple[UUID, str]

# Seconds a failed post waits per attempt before it can be claimed again.
RETRY_BACKOFF_SECONDS = 30


async def fetch_candidate_watchers(
    session: AsyncSession, subreddit: str, eligible_at: datetime
) -> list[Candidate]:
    """Active watchers that follow this subreddit and existed when the post was made.

    A watcher only judges posts made at or after its creation: the hour before it was created is
    the catch-up job's job, so the two never judge the same post. The `@>` containment test is what
    lets the GIN index on `watchers.subreddits` serve this lookup.
    """
    result = await session.execute(
        select(Watcher.id, Watcher.intent_text).where(
            Watcher.status == "active",
            Watcher.subreddits.contains([subreddit]),
            Watcher.created_at <= eligible_at,
        )
    )
    return [(watcher_id, intent_text) for watcher_id, intent_text in result.all()]


def chunk_candidates(candidates: list[Candidate], batch_size: int) -> list[list[Candidate]]:
    """Split candidates into fixed-size groups so one busy subreddit isn't one oversized call."""
    return [candidates[index : index + batch_size] for index in range(0, len(candidates), batch_size)]


async def _lease(session: AsyncSession, posts: list[RedditPost], claim_seconds: int) -> None:
    """Mark claimed posts as owned for `claim_seconds` and count the attempt."""
    locked_until = datetime.now(UTC) + timedelta(seconds=claim_seconds)
    for post in posts:
        post.locked_until = locked_until
        post.attempts = (post.attempts or 0) + 1
    await session.commit()


def _claimable() -> Any:
    """SQL condition: the post is free, or its previous lease has run out."""
    return or_(RedditPost.locked_until.is_(None), RedditPost.locked_until < datetime.now(UTC))


async def claim_post(session: AsyncSession, post_id: UUID, claim_seconds: int) -> RedditPost | None:
    """Claim one specific queued post, or None if it is gone or another worker holds it."""
    result = await session.execute(
        select(RedditPost)
        .where(RedditPost.id == post_id, _claimable())
        .with_for_update(skip_locked=True)
    )
    post = result.scalar_one_or_none()
    if post is not None:
        await _lease(session, [post], claim_seconds)
    return post


async def claim_stale_posts(
    session: AsyncSession, limit: int, min_age_seconds: int, claim_seconds: int
) -> list[RedditPost]:
    """Claim the oldest claimable posts that the ingest-time job has had a fair chance to take."""
    old_enough = datetime.now(UTC) - timedelta(seconds=min_age_seconds)
    result = await session.execute(
        select(RedditPost)
        .where(_claimable(), RedditPost.fetched_at < old_enough)
        .order_by(RedditPost.fetched_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    posts = list(result.scalars())
    if posts:
        await _lease(session, posts, claim_seconds)
    return posts


async def drop_post(session: AsyncSession, post_id: UUID) -> None:
    """Remove a post from the queue; its id stays in `seen_posts`, so it is not re-ingested."""
    await session.execute(delete(RedditPost).where(RedditPost.id == post_id))
    await session.commit()


async def purge_exhausted(session: AsyncSession, max_attempts: int) -> int:
    """Drop queued posts that have used up their attempts — typically a worker that kept dying."""
    result = await session.execute(
        delete(RedditPost).where(RedditPost.attempts >= max_attempts, _claimable())
    )
    await session.commit()
    dropped = result.rowcount or 0
    if dropped:
        logger.error("match: dropped %d post(s) that exhausted %d attempts", dropped, max_attempts)
    return dropped


async def _release(session: AsyncSession, post_id: UUID, attempts: int) -> None:
    """Put a post back in the queue, claimable after a backoff that grows with each attempt."""
    post = await session.get(RedditPost, post_id)
    if post is not None:
        post.locked_until = datetime.now(UTC) + timedelta(
            seconds=RETRY_BACKOFF_SECONDS * max(1, attempts)
        )
        await session.commit()


async def _collect_verdicts(
    verifier: IntentVerifier, post: RedditPost, candidates: list[Candidate], batch_size: int
) -> tuple[dict[UUID, Verdict], bool]:
    """Ask the verifier about every candidate; returns (verdicts by watcher, all-succeeded).

    Stops at the first failed chunk — the whole post is retried, so spending more on the remaining
    chunks now would just be repeated.
    """
    verdicts: dict[UUID, Verdict] = {}
    for chunk in chunk_candidates(candidates, batch_size):
        try:
            batch = await verifier.verify_batch(post.title, post.body or "", chunk)
        except Exception:
            logger.exception(
                "verify: post=%s batch of %d watchers failed",
                post.reddit_post_id,
                len(chunk),
            )
            return verdicts, False
        allowed = {watcher_id for watcher_id, _ in chunk}
        for verdict in batch:
            if verdict.watcher_id in allowed:
                verdicts.setdefault(verdict.watcher_id, verdict)
    return verdicts, len(verdicts) == len(candidates)


async def process_post(
    session: AsyncSession,
    verifier: IntentVerifier,
    settings: Settings,
    post: RedditPost,
    redis: ArqRedis | None = None,
) -> int:
    """Judge one claimed post and settle it; returns how many matches were confirmed.

    Settling is atomic: the outcome is stored and the queue row deleted in one transaction.
    """
    post_id, attempts = post.id, post.attempts
    fields = post_to_dict(post)
    eligible_at = post.posted_at or post.fetched_at

    candidates = await fetch_candidate_watchers(session, post.subreddit, eligible_at)
    if not candidates:
        await drop_post(session, post_id)
        return 0
    # End the read transaction so none is held open across the network calls below.
    await session.commit()

    verdicts, complete = await _collect_verdicts(
        verifier, post, candidates, settings.MATCH_BATCH_SIZE
    )

    if not complete:
        if attempts < settings.MATCH_MAX_ATTEMPTS:
            await _release(session, post_id, attempts)
            return 0
        logger.error(
            "match: post=%s incomplete after %d attempts, settling with %d of %d verdicts",
            post.reddit_post_id,
            attempts,
            len(verdicts),
            len(candidates),
        )
        if not verdicts:
            await drop_post(session, post_id)
            return 0

    outcomes = [
        Outcome(
            watcher_id=verdict.watcher_id,
            post=fields,
            matches=verdict.matches,
            reason=verdict.reason,
            model=verdict.model,
        )
        for verdict in verdicts.values()
    ]
    new_match_ids = await store_outcomes(session, outcomes)
    await session.execute(delete(RedditPost).where(RedditPost.id == post_id))
    await session.commit()

    logger.info(
        "verify: post=%s watchers=%d verdicts=%d confirmed=%d",
        fields["reddit_post_id"],
        len(candidates),
        len(verdicts),
        len(new_match_ids),
    )
    await enqueue_notifications(redis, new_match_ids)
    return len(new_match_ids)


async def match_post(ctx: dict[str, Any], post_id: str) -> int:
    """Arq job: judge one queued post. Enqueued by the ingestion worker when a post is queued."""
    settings: Settings = ctx["settings"]
    async with async_session_factory() as session:
        post = await claim_post(session, UUID(post_id), settings.MATCH_CLAIM_SECONDS)
        if post is None:
            # Already judged, or another worker (or the sweep) has it.
            return 0
        return await process_post(session, ctx["verifier"], settings, post, ctx.get("redis"))


async def backfill(ctx: dict[str, Any]) -> int:
    """Arq cron job: judge queued posts whose ingest-time job never ran or never finished."""
    settings: Settings = ctx["settings"]
    verifier: IntentVerifier = ctx["verifier"]

    handled = 0
    async with async_session_factory() as session:
        await purge_exhausted(session, settings.MATCH_MAX_ATTEMPTS)
        posts = await claim_stale_posts(
            session,
            settings.MATCH_BACKFILL_LIMIT,
            settings.MATCH_BACKFILL_MIN_AGE_SECONDS,
            settings.MATCH_CLAIM_SECONDS,
        )
        for post in posts:
            try:
                await process_post(session, verifier, settings, post, ctx.get("redis"))
                handled += 1
            except Exception:
                logger.exception("match backfill: post=%s failed", post.reddit_post_id)
                await session.rollback()

    if handled:
        logger.info("match backfill: handled=%d", handled)
    return handled


async def catchup_watcher(
    ctx: dict[str, Any], watcher_id: str, subreddits: list[str], until: str
) -> int:
    """Arq job: judge the hour of posts before a watcher (or a newly added subreddit) existed.

    Covers [until - NEW_WATCHER_LOOKBACK_MINUTES, until). Posts from `until` onward reach the
    watcher through the normal queue, so the two windows never overlap. Fetches straight from
    Reddit because anything in that hour that nobody matched has already been deleted here.
    Capped at CATCHUP_MAX_POSTS per subreddit; returns how many matches were confirmed.
    """
    settings: Settings = ctx["settings"]
    verifier: IntentVerifier = ctx["verifier"]
    source: PostSource = ctx["source"]

    until_at = datetime.fromisoformat(until)
    since = until_at - timedelta(minutes=settings.NEW_WATCHER_LOOKBACK_MINUTES)
    new_match_ids = []

    async with async_session_factory() as session:
        watcher = await session.get(Watcher, UUID(watcher_id))
        if watcher is None or watcher.status != "active":
            return 0
        intent_text = watcher.intent_text
        owned_id = watcher.id
        await session.commit()

        for subreddit in subreddits:
            try:
                fetched = await source.fetch_window(
                    subreddit, since, settings.CATCHUP_MAX_POSTS + 20
                )
            except Exception:
                logger.exception("catchup: failed fetching r/%s", subreddit)
                continue

            posts: dict[str, dict[str, Any]] = {}
            for post in fetched:
                posted_at = post.get("posted_at")
                # No timestamp means we can't tell it from a post made after `until`: skip it.
                if posted_at is not None and posted_at < until_at:
                    posts.setdefault(post["reddit_post_id"], post)
            window = list(posts.values())[: settings.CATCHUP_MAX_POSTS]

            for start in range(0, len(window), settings.CATCHUP_BATCH_SIZE):
                chunk = window[start : start + settings.CATCHUP_BATCH_SIZE]
                try:
                    verdicts = await verifier.verify_posts(
                        intent_text,
                        [(p["reddit_post_id"], p["title"], p.get("body") or "") for p in chunk],
                    )
                except Exception:
                    logger.exception("catchup: r/%s batch of %d posts failed", subreddit, len(chunk))
                    continue

                outcomes = [
                    Outcome(
                        watcher_id=owned_id,
                        post=posts[verdict.reddit_post_id],
                        matches=verdict.matches,
                        reason=verdict.reason,
                        model=verdict.model,
                    )
                    for verdict in verdicts
                    if verdict.reddit_post_id in posts
                ]
                new_match_ids.extend(await store_outcomes(session, outcomes))
                await session.commit()

    logger.info(
        "catchup: watcher=%s subreddits=%s confirmed=%d", watcher_id, subreddits, len(new_match_ids)
    )
    await enqueue_notifications(ctx.get("redis"), new_match_ids)
    return len(new_match_ids)


async def retention(ctx: dict[str, Any]) -> dict[str, int]:
    """Arq cron job: prune dedup memory, the rejection sample, and inactive users' matches."""
    async with async_session_factory() as session:
        return await run_retention(session, ctx["settings"])


def backfill_minutes(interval_minutes: int) -> set[int]:
    """Turn a "run every N minutes" setting into the minute set Arq's cron helper expects."""
    interval = max(1, min(60, interval_minutes))
    while 60 % interval != 0:
        interval -= 1
    return {minute for minute in range(60) if minute % interval == 0}


async def startup(ctx: dict[str, Any]) -> None:
    """Arq startup hook: build the verifier and Reddit source once per worker process."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ctx["settings"] = settings
    ctx["verifier"] = build_verifier(settings.OPENAI_API_KEY, settings.VERIFIER_MODEL)
    ctx["source"] = build_source(
        settings.REDDIT_FETCH_MODE,
        settings.REDDIT_CLIENT_ID,
        settings.REDDIT_CLIENT_SECRET,
        settings.REDDIT_USER_AGENT,
    )

    logger.info(
        "matcher starting: verifier=%s batch_size=%d backfill_every=%dm",
        settings.VERIFIER_MODEL,
        settings.MATCH_BATCH_SIZE,
        settings.MATCH_BACKFILL_INTERVAL_MINUTES,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    """Arq shutdown hook: close the verifier's and source's HTTP clients so the process exits."""
    verifier = ctx.get("verifier")
    if verifier is not None:
        await verifier.close()
    source = ctx.get("source")
    if source is not None:
        await source.close()


_settings = get_settings()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [match_post, catchup_watcher]
    cron_jobs: ClassVar[list[Any]] = [
        cron(
            backfill,
            minute=backfill_minutes(_settings.MATCH_BACKFILL_INTERVAL_MINUTES),
            run_at_startup=True,
        ),
        # Hourly, off the sweep's minutes.
        cron(retention, minute={17}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.REDIS_URL)
    queue_name = MATCH_QUEUE
    # Three attempts, then leave it to the backfill sweep.
    max_tries = 3
