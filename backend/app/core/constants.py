"""Shared constants that both the models and the workers need.

Kept here rather than in a worker module so `app.models` never has to import from `app.workers`.
"""

from dataclasses import dataclass

# A watcher the pipeline acts on, versus one the user has switched off.
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUSES = (STATUS_ACTIVE, STATUS_PAUSED)


@dataclass(frozen=True)
class TierLimit:
    max_watchers: int | None
    max_subreddits: int | None
    monthly_price_cents: int


DEFAULT_PLAN = "free"


# From PRD §6. `None` on a limit means unbounded. Enterprise is a real, capped, self-serve Stripe
# price rather than "contact sales" — an uncapped tier at a fixed $49/mo would let one account
# drive unbounded ingestion/LLM cost (see PRD §8 on cost scaling with posts × watchers-per-post).
#
# `max_subreddits` is a pool shared across all of a user's watchers, counted as the *sum* of their
# subreddit lists (PRD's own example spreads 10 as 3/3/4). Note that the ingestion worker polls the
# distinct union, so two watchers both listing r/forhire cost one poll but consume two units of
# quota — the stricter reading, and flagged as an open product decision in docs/PROGRESS.md.
TIER_LIMITS: dict[str, TierLimit] = {
    "free": TierLimit(max_watchers=1, max_subreddits=3, monthly_price_cents=0),
    "standard": TierLimit(max_watchers=3, max_subreddits=10, monthly_price_cents=900),
    "premium": TierLimit(max_watchers=10, max_subreddits=50, monthly_price_cents=2900),
    "enterprise": TierLimit(max_watchers=25, max_subreddits=150, monthly_price_cents=4900),
}

# Plans billed through Stripe — every tier except the free one. Drives the checkout price-id
# lookup and the pricing table in services/billing.py.
PAID_PLANS: tuple[str, ...] = tuple(plan for plan in TIER_LIMITS if plan != DEFAULT_PLAN)


# Look up a plan's limits, falling back to the free tier for an unrecognised plan string.
# Failing closed matters: a typo in a plan name should not silently grant unlimited watchers.
def limits_for_plan(plan: str) -> TierLimit:
    return TIER_LIMITS.get(plan, TIER_LIMITS[DEFAULT_PLAN])
