"""Plan limit enforcement for watchers.

Kept out of the endpoint module so the arithmetic is testable without HTTP, and so there is one
place to look when the tier table changes. The limits themselves live in `app.core.constants`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TierLimit, limits_for_plan
from app.models.user import User
from app.models.watcher import Watcher


@dataclass(frozen=True)
class Usage:
    watchers: int
    subreddits: int


class LimitExceeded(Exception):
    """Raised when a write would take a user past their plan. Carries a user-facing message.

    The message names the limit *and* the current usage on purpose — "limit exceeded" alone forces
    the user to go and count their own watchers to work out what happened.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# Count a user's watchers and their total subreddit allocation.
#
# `exclude_watcher_id` leaves one watcher out of the count, which is what makes an edit check
# correct: updating a watcher must compare against everything *else* the user owns, not against a
# total that still includes the row's old values.
async def current_usage(
    session: AsyncSession, user_id: uuid.UUID, exclude_watcher_id: uuid.UUID | None = None
) -> Usage:
    query = select(Watcher.subreddits).where(Watcher.user_id == user_id)
    if exclude_watcher_id is not None:
        query = query.where(Watcher.id != exclude_watcher_id)

    rows = list((await session.execute(query)).scalars())
    # Sum of list lengths, per PRD §6's 3/3/4 example — not a distinct count across watchers.
    return Usage(watchers=len(rows), subreddits=sum(len(row) for row in rows))


# Decide whether a create or edit fits inside the user's plan.
#
# `adding_watcher` is False for an edit: the row already exists, so only its subreddits move.
def check_limits(
    plan: str, usage: Usage, new_subreddit_count: int, adding_watcher: bool
) -> None:
    limit: TierLimit = limits_for_plan(plan)

    if (
        adding_watcher
        and limit.max_watchers is not None
        and usage.watchers + 1 > limit.max_watchers
    ):
        raise LimitExceeded(
            f"Your {plan} plan allows {limit.max_watchers} "
            f"watcher{'s' if limit.max_watchers != 1 else ''}; you already have "
            f"{usage.watchers}."
        )

    if limit.max_subreddits is not None:
        total = usage.subreddits + new_subreddit_count
        if total > limit.max_subreddits:
            raise LimitExceeded(
                f"Your {plan} plan allows {limit.max_subreddits} subreddits across all watchers. "
                f"This would bring you to {total} "
                f"({usage.subreddits} already in use, {new_subreddit_count} requested)."
            )


# Convenience wrapper for the endpoints: read usage, then check it.
async def enforce_limits(
    session: AsyncSession,
    user: User,
    new_subreddit_count: int,
    adding_watcher: bool,
    exclude_watcher_id: uuid.UUID | None = None,
) -> None:
    usage = await current_usage(session, user.id, exclude_watcher_id)
    check_limits(user.plan, usage, new_subreddit_count, adding_watcher)


# Total usage for the /me endpoint. Separate from `current_usage` only in that it never excludes.
async def usage_for_user(session: AsyncSession, user_id: uuid.UUID) -> Usage:
    return await current_usage(session, user_id)


# Count how many watchers a user has, as a cheap COUNT rather than loading every subreddit list.
# Used where only the watcher count matters.
async def count_watchers(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(Watcher).where(Watcher.user_id == user_id)
    )
    return int(result.scalar_one())
