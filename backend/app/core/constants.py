"""Shared constants that both the models and the workers need.

Kept here rather than in a worker module so `app.models` never has to import from `app.workers`.
"""

from dataclasses import dataclass

# Output width of OpenAI's `text-embedding-3-small`. This is baked into the pgvector column type,
# so changing it means a migration plus re-embedding every row — it is not a runtime setting.
EMBEDDING_DIMENSIONS = 1536

# What a watcher is looking for: someone asking for work, or someone advertising it.
DIRECTION_REQUESTING = "requesting"
DIRECTION_OFFERING = "offering"
DIRECTIONS = (DIRECTION_REQUESTING, DIRECTION_OFFERING)

# A watcher the pipeline acts on, versus one the user has switched off.
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUSES = (STATUS_ACTIVE, STATUS_PAUSED)


@dataclass(frozen=True)
class TierLimit:
    max_watchers: int | None
    max_subreddits: int | None


# From PRD §6. `None` means unbounded — Enterprise limits are negotiated, not encoded.
#
# `max_subreddits` is a pool shared across all of a user's watchers, counted as the *sum* of their
# subreddit lists (PRD's own example spreads 10 as 3/3/4). Note that the ingestion worker polls the
# distinct union, so two watchers both listing r/forhire cost one poll but consume two units of
# quota — the stricter reading, and flagged as an open product decision in docs/PROGRESS.md.
TIER_LIMITS: dict[str, TierLimit] = {
    "free": TierLimit(max_watchers=1, max_subreddits=3),
    "standard": TierLimit(max_watchers=3, max_subreddits=10),
    "premium": TierLimit(max_watchers=10, max_subreddits=50),
    "enterprise": TierLimit(max_watchers=None, max_subreddits=None),
}

DEFAULT_PLAN = "free"


# Look up a plan's limits, falling back to the free tier for an unrecognised plan string.
# Failing closed matters: a typo in a plan name should not silently grant unlimited watchers.
def limits_for_plan(plan: str) -> TierLimit:
    return TIER_LIMITS.get(plan, TIER_LIMITS[DEFAULT_PLAN])
