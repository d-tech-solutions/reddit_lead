"""Embedding worker: turns stored posts and watcher intents into pgvector rows.

Runs as an Arq consumer (`arq app.workers.embed.WorkerSettings`), unlike the ingestion worker which
is a plain interval loop. Two things trigger work:

* jobs enqueued by the ingestion worker the moment a post is inserted (low latency), and
* a periodic backfill sweep over rows whose embedding is still NULL (the safety net).

The sweep exists because a queue alone loses work: posts stored before this worker existed were
never enqueued, a job that exhausts its retries would vanish, and watchers have no CRUD API yet to
enqueue from. Anything the queue misses, the sweep picks up on its next pass.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

from arq import cron
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.reddit_post import RedditPost
from app.models.watcher import Watcher
from app.workers.embedding_source import (
    EmbeddingProvider,
    build_embedding_provider,
    post_to_text,
)

logger = logging.getLogger(__name__)


# Split a list into fixed-size chunks so one oversized sweep doesn't become one oversized API call.
def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


# Embed the given posts and write the vectors back. Returns how many rows were updated.
# Posts with no usable text are skipped rather than sent to the API, which rejects empty input.
async def embed_posts(
    session: AsyncSession,
    provider: EmbeddingProvider,
    posts: list[RedditPost],
    batch_size: int,
    redis: ArqRedis | None = None,
) -> int:
    pairs = [(post, post_to_text(post.title, post.body or "")) for post in posts]
    usable = [(post, text) for post, text in pairs if text]
    for post, _ in ((p, t) for p, t in pairs if not t):
        logger.warning("embed: post %s has no title or body, skipping", post.reddit_post_id)

    updated = 0
    embedded: list[RedditPost] = []
    for batch in _chunked(usable, batch_size):
        vectors = await provider.embed([text for _, text in batch])
        now = datetime.now(UTC)
        for (post, _), vector in zip(batch, vectors, strict=True):
            post.embedding = vector
            post.embedded_at = now
            embedded.append(post)
        updated += len(batch)

    if updated:
        await session.commit()
        # Hand off only after the commit, so the matcher can never read a row that is not there.
        await enqueue_for_matching(redis, [post.id for post in embedded])
    return updated


# Hand newly embedded post ids to the matcher. Non-fatal for the same reason the ingestion
# worker's enqueue is: the matcher has its own backfill sweep, so a lost job is recoverable but a
# crashed embedding worker is not.
async def enqueue_for_matching(redis: ArqRedis | None, post_ids: list[uuid.UUID]) -> None:
    if redis is None or not post_ids:
        return

    for post_id in post_ids:
        try:
            await redis.enqueue_job("match_post", str(post_id), _job_id=f"match_post:{post_id}")
        except Exception:
            logger.exception("embed: failed enqueueing match job for post %s", post_id)


# Embed the intent text of the given watchers and write the vectors back.
# Returns how many rows were updated.
async def embed_watchers(
    session: AsyncSession,
    provider: EmbeddingProvider,
    watchers: list[Watcher],
    batch_size: int,
) -> int:
    pairs = [(watcher, (watcher.intent_text or "").strip()) for watcher in watchers]
    usable = [(watcher, text) for watcher, text in pairs if text]
    for watcher, _ in ((w, t) for w, t in pairs if not t):
        logger.warning("embed: watcher %s has empty intent_text, skipping", watcher.id)

    updated = 0
    for batch in _chunked(usable, batch_size):
        vectors = await provider.embed([text for _, text in batch])
        now = datetime.now(UTC)
        for (watcher, _), vector in zip(batch, vectors, strict=True):
            watcher.intent_embedding = vector
            watcher.embedded_at = now
        updated += len(batch)

    if updated:
        await session.commit()
    return updated


# Load posts that still have no embedding, oldest first so the backlog drains in arrival order.
async def fetch_posts_needing_embedding(session: AsyncSession, limit: int) -> list[RedditPost]:
    result = await session.execute(
        select(RedditPost)
        .where(RedditPost.embedding.is_(None))
        .order_by(RedditPost.fetched_at)
        .limit(limit)
    )
    return list(result.scalars())


# Load watchers whose intent text has not been embedded yet. Only active ones matter — the matcher
# ignores the rest, so embedding them would be spend with no payoff.
async def fetch_watchers_needing_embedding(session: AsyncSession, limit: int) -> list[Watcher]:
    result = await session.execute(
        select(Watcher)
        .where(Watcher.intent_embedding.is_(None), Watcher.status == "active")
        .order_by(Watcher.created_at)
        .limit(limit)
    )
    return list(result.scalars())


# Arq job: embed one post, enqueued by the ingestion worker right after insert.
# A failure here leaves `embedding` NULL, so the backfill sweep retries it later.
async def embed_post(ctx: dict[str, Any], post_id: str) -> int:
    provider: EmbeddingProvider = ctx["provider"]
    settings = ctx["settings"]

    async with async_session_factory() as session:
        post = await session.get(RedditPost, UUID(post_id))
        if post is None:
            logger.warning("embed_post: post %s no longer exists", post_id)
            return 0
        if post.embedding is not None:
            return 0
        return await embed_posts(
            session, provider, [post], settings.EMBEDDING_BATCH_SIZE, ctx.get("redis")
        )


# Arq job: embed one watcher's intent text. Enqueue this whenever `intent_text` is created or
# edited — the stored vector is otherwise stale and the matcher would compare against old wording.
async def embed_watcher(ctx: dict[str, Any], watcher_id: str, force: bool = False) -> int:
    provider: EmbeddingProvider = ctx["provider"]
    settings = ctx["settings"]

    async with async_session_factory() as session:
        watcher = await session.get(Watcher, UUID(watcher_id))
        if watcher is None:
            logger.warning("embed_watcher: watcher %s no longer exists", watcher_id)
            return 0
        if watcher.intent_embedding is not None and not force:
            return 0
        return await embed_watchers(session, provider, [watcher], settings.EMBEDDING_BATCH_SIZE)


# Arq cron job: catch anything the queue missed. Cheap when there is nothing to do, since the
# partial indexes on the NULL rows make both lookups an index scan.
async def backfill(ctx: dict[str, Any]) -> int:
    provider: EmbeddingProvider = ctx["provider"]
    settings = ctx["settings"]

    async with async_session_factory() as session:
        watchers = await fetch_watchers_needing_embedding(session, settings.EMBED_BACKFILL_LIMIT)
        watcher_count = await embed_watchers(
            session, provider, watchers, settings.EMBEDDING_BATCH_SIZE
        )

        posts = await fetch_posts_needing_embedding(session, settings.EMBED_BACKFILL_LIMIT)
        post_count = await embed_posts(
            session, provider, posts, settings.EMBEDDING_BATCH_SIZE, ctx.get("redis")
        )

    if watcher_count or post_count:
        logger.info("backfill: embedded watchers=%d posts=%d", watcher_count, post_count)
    return watcher_count + post_count


# Turn a "run every N minutes" setting into the minute set Arq's cron helper expects.
# Falls back to the nearest divisor of 60 so an awkward value still yields an even schedule.
def backfill_minutes(interval_minutes: int) -> set[int]:
    interval = max(1, min(60, interval_minutes))
    while 60 % interval != 0:
        interval -= 1
    return {minute for minute in range(60) if minute % interval == 0}


# Arq startup hook: build the embedding provider once per worker process rather than per job,
# so the underlying HTTP connection pool is reused.
async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ctx["settings"] = settings
    ctx["provider"] = build_embedding_provider(settings.OPENAI_API_KEY, settings.EMBEDDING_MODEL)
    logger.info(
        "embedding worker starting: model=%s batch=%d backfill_every=%dm",
        settings.EMBEDDING_MODEL,
        settings.EMBEDDING_BATCH_SIZE,
        settings.EMBED_BACKFILL_INTERVAL_MINUTES,
    )


# Arq shutdown hook: close the provider's HTTP client so the process exits without warnings.
async def shutdown(ctx: dict[str, Any]) -> None:
    provider = ctx.get("provider")
    if provider is not None:
        await provider.close()


_settings = get_settings()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [embed_post, embed_watcher]
    cron_jobs: ClassVar[list[Any]] = [
        cron(
            backfill,
            minute=backfill_minutes(_settings.EMBED_BACKFILL_INTERVAL_MINUTES),
            run_at_startup=True,
        )
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.REDIS_URL)
    # Three attempts, then give up and let the backfill sweep retry on its own schedule.
    max_tries = 3
