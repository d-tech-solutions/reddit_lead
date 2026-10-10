"""Retention jobs: keep every table that grows with traffic bounded.

All deletes run in small batches (`LIMIT n` inside a subquery) with a commit after each, so a large
purge never holds a long lock or builds a huge transaction, and each batch is served by an index:

- `seen_posts`    by `seen_at`           — dedup memory only needs to outlive the ingest window
- `rejection_log` by `created_at`        — a short sample of what the verifier rejected
- `matches`       by the owner's `users.last_active_at` — gone after USER_INACTIVITY_RETENTION_DAYS
- `matched_posts` with no remaining `matches` row    — nothing references them anymore
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Safety valve: one run never loops more than this many batches (batch_size * MAX_BATCHES rows).
MAX_BATCHES = 500

# A matched post is only treated as orphaned once it is this old, so a row can never be collected
# in the instant between its insert and the matches that reference it.
ORPHAN_GRACE = timedelta(hours=1)


async def _delete_in_batches(session: AsyncSession, sql: str, params: dict[str, Any]) -> int:
    """Run a `DELETE ... LIMIT :batch` statement until it stops deleting full batches."""
    total = 0
    batch = params["batch"]
    for _ in range(MAX_BATCHES):
        result = await session.execute(text(sql), params)
        await session.commit()
        deleted = result.rowcount or 0
        total += deleted
        if deleted < batch:
            break
    return total


async def prune_seen_posts(session: AsyncSession, days: int, batch: int) -> int:
    """Forget post ids older than the dedup window."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return await _delete_in_batches(
        session,
        "DELETE FROM seen_posts WHERE reddit_post_id IN ("
        "SELECT reddit_post_id FROM seen_posts WHERE seen_at < :cutoff LIMIT :batch)",
        {"cutoff": cutoff, "batch": batch},
    )


async def prune_rejection_log(session: AsyncSession, days: int, batch: int) -> int:
    """Drop rejection samples older than the retention window."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return await _delete_in_batches(
        session,
        "DELETE FROM rejection_log WHERE id IN ("
        "SELECT id FROM rejection_log WHERE created_at < :cutoff LIMIT :batch)",
        {"cutoff": cutoff, "batch": batch},
    )


async def purge_inactive_user_matches(session: AsyncSession, days: int, batch: int) -> int:
    """Delete the matches of users with no authenticated request for `days` days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return await _delete_in_batches(
        session,
        "DELETE FROM matches WHERE id IN ("
        "SELECT m.id FROM users u "
        "JOIN watchers w ON w.user_id = u.id "
        "JOIN matches m ON m.watcher_id = w.id "
        "WHERE u.last_active_at < :cutoff LIMIT :batch)",
        {"cutoff": cutoff, "batch": batch},
    )


async def purge_orphan_matched_posts(session: AsyncSession, batch: int) -> int:
    """Delete matched posts that no match references anymore."""
    cutoff = datetime.now(UTC) - ORPHAN_GRACE
    return await _delete_in_batches(
        session,
        "DELETE FROM matched_posts WHERE id IN ("
        "SELECT mp.id FROM matched_posts mp WHERE mp.matched_at < :cutoff "
        "AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.matched_post_id = mp.id) "
        "LIMIT :batch)",
        {"cutoff": cutoff, "batch": batch},
    )


async def run_retention(session: AsyncSession, settings: Settings) -> dict[str, int]:
    """Run every retention job once; returns how many rows each removed."""
    batch = settings.RETENTION_BATCH_SIZE
    counts = {
        "seen_posts": await prune_seen_posts(session, settings.SEEN_POSTS_RETENTION_DAYS, batch),
        "rejection_log": await prune_rejection_log(
            session, settings.REJECTION_LOG_RETENTION_DAYS, batch
        ),
        "inactive_matches": await purge_inactive_user_matches(
            session, settings.USER_INACTIVITY_RETENTION_DAYS, batch
        ),
        "orphan_matched_posts": await purge_orphan_matched_posts(session, batch),
    }
    if any(counts.values()):
        logger.info("retention: %s", counts)
    return counts
