"""Best-effort access to the Arq queue from the API process.

The API only ever enqueues one thing: the catch-up job for a new watcher. That job is a bonus (the
hour of posts before the watcher existed), so a Redis outage must never fail watcher creation —
every failure here is logged and swallowed.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import MATCH_QUEUE, get_settings

logger = logging.getLogger(__name__)

_pool: ArqRedis | None = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> ArqRedis:
    """Create the shared pool on first use; concurrent first callers build it once."""
    global _pool
    async with _pool_lock:
        if _pool is None:
            redis_settings = RedisSettings.from_dsn(get_settings().REDIS_URL)
            # Fail fast: this runs inside a user's request.
            redis_settings.conn_timeout = 2
            redis_settings.conn_retries = 1
            _pool = await create_pool(redis_settings)
        return _pool


async def close_pool() -> None:
    """Close the shared pool at API shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue_catchup(watcher_id: uuid.UUID, subreddits: list[str], until: datetime) -> None:
    """Ask the matcher to judge the hour of posts before `until` for these subreddits.

    `until` is the moment the watcher (or the new subreddit) started counting, so the catch-up
    window [until - lookback, until) and the normal queue (posts from `until` on) never overlap.
    """
    if not subreddits:
        return
    try:
        pool = await _get_pool()
        await pool.enqueue_job(
            "catchup_watcher",
            str(watcher_id),
            subreddits,
            until.isoformat(),
            _job_id=f"catchup:{watcher_id}:{int(until.timestamp())}",
            _queue_name=MATCH_QUEUE,
        )
    except Exception:
        logger.exception("queue: failed enqueueing catch-up for watcher %s", watcher_id)
