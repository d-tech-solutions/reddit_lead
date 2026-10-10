"""Superadmin operations: list/inspect every account, change plan or active status, delete.

Kept separate from `services/account.py` (self-service delete) and `services/limits.py` (plan
enforcement) even though this reuses both — this module is the one place that acts on *someone
else's* account rather than the caller's own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import STATUS_PAUSED, TIER_LIMITS
from app.models.user import User
from app.models.watcher import Watcher


class UnknownPlan(Exception):
    """Raised for a plan string that isn't one of `TIER_LIMITS`' keys."""

    def __init__(self, plan: str) -> None:
        super().__init__(f"Unknown plan: {plan!r}")
        self.plan = plan


@dataclass(frozen=True)
class AdminUserRow:
    user: User
    watcher_count: int


# Every account, newest first, with a per-user watcher count in the same query rather than N+1.
# `search` does a case-insensitive substring match on email; `None`/empty skips the filter.
async def list_users(
    session: AsyncSession, search: str | None = None, limit: int = 50, offset: int = 0
) -> list[AdminUserRow]:
    count_subquery = (
        select(func.count())
        .select_from(Watcher)
        .where(Watcher.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    query = select(User, count_subquery).order_by(User.created_at.desc())
    if search:
        query = query.where(User.email.ilike(f"%{search}%"))
    query = query.limit(limit).offset(offset)

    rows = await session.execute(query)
    return [AdminUserRow(user=user, watcher_count=count) for user, count in rows.all()]


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


# Every watcher a user has created, for the admin detail view.
async def list_user_watchers(session: AsyncSession, user_id: uuid.UUID) -> list[Watcher]:
    result = await session.execute(
        select(Watcher).where(Watcher.user_id == user_id).order_by(Watcher.created_at.desc())
    )
    return list(result.scalars())


# Set a user's plan directly, bypassing Stripe. Does not touch the `subscriptions` table, so a plan
# set this way can be overwritten by the next webhook event if the user has an active subscription
# — fine for comping/downgrading a free account, worth a warning in the UI for anyone else.
def set_user_plan(user: User, plan: str) -> None:
    if plan not in TIER_LIMITS:
        raise UnknownPlan(plan)
    user.plan = plan


# Activate or deactivate a user. Deactivating also force-pauses every one of their watchers so the
# pipeline stops spending on them immediately; reactivating only clears the flag — it does not
# guess which watchers to resume.
async def set_user_active(session: AsyncSession, user: User, active: bool) -> None:
    user.is_active = active
    if not active:
        await session.execute(
            Watcher.__table__.update()
            .where(Watcher.user_id == user.id)
            .values(status=STATUS_PAUSED)
        )
