"""Ingestion worker: polls subreddits for new posts and stores unseen ones.

Runs as its own process (`python -m app.workers.ingest`), not as an Arq consumer — it is a
producer at the head of the pipeline, so a plain interval loop is all it needs.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.reddit_post import RedditPost
from app.models.watcher import Watcher
from app.workers.reddit_source import PostSource, build_source

logger = logging.getLogger(__name__)

POSTS_PER_FETCH = 50


async def get_active_subreddits(session: AsyncSession) -> list[str]:
    result = await session.execute(select(Watcher.subreddits).where(Watcher.status == "active"))
    distinct = {sub for row in result.scalars() for sub in row}
    return sorted(distinct)


async def store_posts(session: AsyncSession, posts: list[dict[str, Any]]) -> list[uuid.UUID]:
    """Insert posts, skipping ones already stored; returns ids of the newly inserted rows."""
    if not posts:
        return []

    statement = (
        insert(RedditPost)
        .values(posts)
        .on_conflict_do_nothing(index_elements=["reddit_post_id"])
        .returning(RedditPost.id)
    )
    result = await session.execute(statement)
    inserted = list(result.scalars().all())
    await session.commit()
    return inserted


async def enqueue_for_matching(redis: ArqRedis | None, post_ids: list[uuid.UUID]) -> None:
    """Hand new post ids to the matcher.

    Deliberately non-fatal: ingestion must not stop because the next stage is unreachable, and the
    matcher's own backfill sweep catches anything that never made it onto the queue.
    """
    if redis is None or not post_ids:
        return

    for post_id in post_ids:
        try:
            # A job id derived from the post id makes a duplicate enqueue a no-op.
            await redis.enqueue_job("match_post", str(post_id), _job_id=f"match_post:{post_id}")
        except Exception:
            logger.exception("ingest: failed enqueueing match job for post %s", post_id)


async def poll_once(
    session: AsyncSession, source: PostSource, redis: ArqRedis | None = None
) -> int:
    """Run one full poll cycle: fetch every active subreddit, store what's new, and enqueue it for
    matching. Returns the total number of new posts stored."""
    subreddits = await get_active_subreddits(session)
    if not subreddits:
        logger.info("ingest cycle: no active watchers, nothing to poll")
        return 0

    total_new = 0
    for subreddit in subreddits:
        try:
            posts = await source.fetch(subreddit, POSTS_PER_FETCH)
        except Exception:
            logger.exception("ingest: failed fetching r/%s", subreddit)
            continue

        new_ids = await store_posts(session, posts)
        await enqueue_for_matching(redis, new_ids)
        new_count = len(new_ids)
        total_new += new_count
        logger.info("ingest: r/%s fetched=%d new=%d", subreddit, len(posts), new_count)

    logger.info("ingest cycle complete: subreddits=%d new_posts=%d", len(subreddits), total_new)
    return total_new


async def main() -> None:
    """Process entry point: build the configured post source, connect to Redis, then loop
    `poll_once` forever on `REDDIT_POLL_INTERVAL_SECONDS`, cleaning up both on exit."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    source = build_source(
        settings.REDDIT_FETCH_MODE,
        settings.REDDIT_CLIENT_ID,
        settings.REDDIT_CLIENT_SECRET,
        settings.REDDIT_USER_AGENT,
    )
    logger.info(
        "ingestion worker starting: mode=%s interval=%ds",
        settings.REDDIT_FETCH_MODE,
        settings.REDDIT_POLL_INTERVAL_SECONDS,
    )

    # A missing Redis is survivable — posts still get stored, and the matcher's backfill sweep
    # will pick them up — so a failed connection is logged rather than fatal.
    redis: ArqRedis | None = None
    try:
        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    except Exception:
        logger.exception("ingest: could not connect to Redis, match jobs will not be enqueued")

    try:
        while True:
            async with async_session_factory() as session:
                await poll_once(session, source, redis)
            await asyncio.sleep(settings.REDDIT_POLL_INTERVAL_SECONDS)
    finally:
        await source.close()
        if redis is not None:
            await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
