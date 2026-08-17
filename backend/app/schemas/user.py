import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UsageRead(BaseModel):
    """Current consumption against the plan's limits. `None` on a limit means unbounded.

    Returned alongside the user so the UI can render "1 of 3 watchers" without re-deriving the
    tier table on the frontend — one source of truth for the numbers.
    """

    watchers_used: int
    watchers_limit: int | None
    subreddits_used: int
    subreddits_limit: int | None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    plan: str
    created_at: datetime


class MeRead(BaseModel):
    user: UserRead
    usage: UsageRead
    # Confirmed matches the user has not opened yet. Bundled here so the nav badge renders from the
    # call the dashboard already makes, rather than costing a second request on every page.
    unread_matches: int = 0
