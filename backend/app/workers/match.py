"""Matcher worker: pick candidate watchers for each embedded post, then have Claude judge them.

Runs as an Arq consumer (`arq app.workers.match.WorkerSettings`), triggered by the embedding
worker the moment a post's vector lands, with a backfill sweep as the safety net — same two-trigger
shape as the embedding worker, for the same reasons (docs/embedding-worker/README.md §3).

Two stages per post:

1. **Vector gate (recall).** Find active watchers whose subreddit list covers this post, score
   them by cosine similarity minus a direction penalty, and keep the top K. Deliberately loose:
   a false positive here costs one cheap LLM call, a false negative is silent and unrecoverable.
2. **Verifier (precision).** Claude answers yes or no per candidate. Its verdict is what reaches
   the user.

Every candidate is written to `matches` whether it passes or fails, with its similarity, direction
score, and verdict. That log is the only way to eventually calibrate K from real traffic instead of
guessing (ARCHITECTURE.md, Matcher section).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.match import Match
from app.models.reddit_post import RedditPost
from app.models.watcher import Watcher
from app.workers.direction import compute_direction_axis, direction_penalty, direction_score
from app.workers.embedding_source import build_embedding_provider
from app.workers.verifier import IntentVerifier, build_verifier

logger = logging.getLogger(__name__)


# Cosine similarity between two vectors that are not assumed to be unit length.
def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_len = sum(a * a for a in left) ** 0.5
    right_len = sum(b * b for b in right) ** 0.5
    if left_len == 0 or right_len == 0:
        return 0.0
    return dot / (left_len * right_len)


# Load the active, embedded watchers that cover this post's subreddit.
# Filtering by subreddit in SQL keeps the candidate set small before any vector maths.
async def fetch_candidate_watchers(session: AsyncSession, subreddit: str) -> list[Watcher]:
    result = await session.execute(
        select(Watcher).where(
            Watcher.status == "active",
            Watcher.intent_embedding.is_not(None),
            Watcher.subreddits.any(subreddit),
        )
    )
    return list(result.scalars())


# Score every candidate watcher against one post and return the best K, highest first.
#
# The direction penalty depends on the post *and* the watcher's `direction`, so it does not
# reorder watchers that all want the same side — its job there is to push the whole candidate set
# down below the gate when the post points the wrong way. Across watchers wanting opposite sides,
# it separates them correctly.
def rank_watchers(
    post_embedding: list[float],
    watchers: list[Watcher],
    axis: list[float],
    weight: float,
    top_k: int,
) -> list[tuple[Watcher, float, float, float]]:
    post_direction = direction_score(post_embedding, axis)

    scored: list[tuple[Watcher, float, float, float]] = []
    for watcher in watchers:
        similarity = cosine(watcher.intent_embedding, post_embedding)
        penalty = direction_penalty(post_direction, watcher.direction)
        scored.append((watcher, similarity, post_direction, similarity - weight * penalty))

    scored.sort(key=lambda row: row[3], reverse=True)
    return scored[:top_k]


# Write one candidate row per (watcher, post), skipping pairs already recorded.
# Returns the ids of rows genuinely inserted, so a re-run does not re-verify old candidates.
async def store_candidates(
    session: AsyncSession,
    post_id: UUID,
    ranked: list[tuple[Watcher, float, float, float]],
) -> list[UUID]:
    if not ranked:
        return []

    rows = [
        {
            "watcher_id": watcher.id,
            "reddit_post_id": post_id,
            "similarity": similarity,
            "direction_score": post_direction,
            "adjusted_score": adjusted,
        }
        for watcher, similarity, post_direction, adjusted in ranked
    ]

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


# Run the vector gate for one post. Returns the ids of new candidate rows awaiting a verdict.
async def gate_post(
    session: AsyncSession, post: RedditPost, axis: list[float], settings: Any
) -> list[UUID]:
    watchers = await fetch_candidate_watchers(session, post.subreddit)
    if not watchers:
        return []

    ranked = rank_watchers(
        post.embedding,
        watchers,
        axis,
        settings.MATCH_DIRECTION_WEIGHT,
        settings.MATCH_TOP_K,
    )
    candidate_ids = await store_candidates(session, post.id, ranked)
    logger.info(
        "gate: post=%s subreddit=r/%s watchers=%d candidates=%d",
        post.reddit_post_id,
        post.subreddit,
        len(watchers),
        len(candidate_ids),
    )
    return candidate_ids


# Ask the verifier about one candidate row and record the verdict.
# On API failure the row is left NULL so the backfill sweep retries it.
async def verify_candidate(
    session: AsyncSession, verifier: IntentVerifier, match_id: UUID
) -> bool | None:
    match = await session.get(Match, match_id)
    if match is None or match.llm_verified is not None:
        return None

    watcher = await session.get(Watcher, match.watcher_id)
    post = await session.get(RedditPost, match.reddit_post_id)
    if watcher is None or post is None:
        logger.warning("verify: match %s references a missing row, skipping", match_id)
        return None

    verdict = await verifier.verify(
        watcher.intent_text, watcher.direction, post.title, post.body or ""
    )

    match.llm_verified = verdict.matches
    match.llm_reason = verdict.reason
    match.llm_model = verdict.model
    match.verified_at = datetime.now(UTC)
    await session.commit()

    logger.info(
        "verify: post=%s watcher=%s similarity=%.3f direction=%+.3f verdict=%s reason=%s",
        post.reddit_post_id,
        watcher.name,
        match.similarity,
        match.direction_score,
        verdict.matches,
        verdict.reason,
    )
    return verdict.matches


# Arq job: gate one post, then verify each new candidate.
# Enqueued by the embedding worker once the post has a vector.
async def match_post(ctx: dict[str, Any], post_id: str) -> int:
    axis: list[float] = ctx["axis"]
    verifier: IntentVerifier = ctx["verifier"]
    settings = ctx["settings"]

    async with async_session_factory() as session:
        post = await session.get(RedditPost, UUID(post_id))
        if post is None:
            logger.warning("match_post: post %s no longer exists", post_id)
            return 0
        if post.embedding is None:
            logger.warning("match_post: post %s has no embedding yet, skipping", post_id)
            return 0

        candidate_ids = await gate_post(session, post, axis, settings)

        confirmed = 0
        for match_id in candidate_ids:
            if await verify_candidate(session, verifier, match_id):
                confirmed += 1

    return confirmed


# Load candidate rows that no verdict has been recorded for, oldest first.
async def fetch_unverified(session: AsyncSession, limit: int) -> list[UUID]:
    result = await session.execute(
        select(Match.id)
        .where(Match.llm_verified.is_(None))
        .order_by(Match.created_at)
        .limit(limit)
    )
    return list(result.scalars())


# Load embedded posts that the gate has never run against.
# `NOT EXISTS` rather than a join so a post with zero candidates is not re-gated forever — it gets
# one row per matching watcher, and with no matching watchers there is nothing to write. Posts in
# subreddits nobody watches are therefore re-checked each sweep, which is cheap and also correct:
# a watcher added later should pick them up.
async def fetch_ungated_posts(session: AsyncSession, limit: int) -> list[RedditPost]:
    gated = select(Match.reddit_post_id).where(Match.reddit_post_id == RedditPost.id)
    result = await session.execute(
        select(RedditPost)
        .where(RedditPost.embedding.is_not(None), ~gated.exists())
        .order_by(RedditPost.fetched_at)
        .limit(limit)
    )
    return list(result.scalars())


# Arq cron job: catch posts the queue never gated and candidates whose verification failed.
async def backfill(ctx: dict[str, Any]) -> int:
    axis: list[float] = ctx["axis"]
    verifier: IntentVerifier = ctx["verifier"]
    settings = ctx["settings"]

    handled = 0
    async with async_session_factory() as session:
        # Verify first: unjudged candidates are already-paid-for work waiting on a verdict.
        for match_id in await fetch_unverified(session, settings.MATCH_BACKFILL_LIMIT):
            await verify_candidate(session, verifier, match_id)
            handled += 1

        for post in await fetch_ungated_posts(session, settings.MATCH_BACKFILL_LIMIT):
            candidate_ids = await gate_post(session, post, axis, settings)
            for match_id in candidate_ids:
                await verify_candidate(session, verifier, match_id)
                handled += 1

    if handled:
        logger.info("match backfill: handled=%d", handled)
    return handled


# Turn a "run every N minutes" setting into the minute set Arq's cron helper expects.
# Duplicated from the embedding worker rather than shared: the two workers are deployed
# separately and a shared helper would couple their schedules.
def backfill_minutes(interval_minutes: int) -> set[int]:
    interval = max(1, min(60, interval_minutes))
    while 60 % interval != 0:
        interval -= 1
    return {minute for minute in range(60) if minute % interval == 0}


# Arq startup hook: build the verifier and compute the direction axis once per process.
# The axis costs one embedding call; recomputing it per job would be pure waste.
async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ctx["settings"] = settings
    ctx["verifier"] = build_verifier(settings.ANTHROPIC_API_KEY, settings.VERIFIER_MODEL)

    provider = build_embedding_provider(settings.OPENAI_API_KEY, settings.EMBEDDING_MODEL)
    try:
        ctx["axis"] = await compute_direction_axis(provider)
    finally:
        await provider.close()

    logger.info(
        "matcher starting: verifier=%s top_k=%d direction_weight=%.2f backfill_every=%dm",
        settings.VERIFIER_MODEL,
        settings.MATCH_TOP_K,
        settings.MATCH_DIRECTION_WEIGHT,
        settings.MATCH_BACKFILL_INTERVAL_MINUTES,
    )


# Arq shutdown hook: close the verifier's HTTP client so the process exits cleanly.
async def shutdown(ctx: dict[str, Any]) -> None:
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
    # Three attempts, then leave it to the backfill sweep.
    max_tries = 3
