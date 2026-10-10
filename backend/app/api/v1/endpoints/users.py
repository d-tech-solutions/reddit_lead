"""The current-user endpoint. Creates the account row on first call, via `get_current_user`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.core.constants import limits_for_plan
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import MeRead, UsageRead, UserRead
from app.services.account import delete_account
from app.services.limits import usage_for_user
from app.services.matches import unread_count

router = APIRouter(tags=["users"])


# Return the caller's account plus what they have used against their plan.
# Bundling usage here saves the UI a second round trip and keeps the tier numbers server-side.
@router.get("/me", response_model=MeRead)
async def read_me(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeRead:
    usage = await usage_for_user(session, user.id)
    limit = limits_for_plan(user.plan)
    unread = await unread_count(session, user.id)

    return MeRead(
        user=UserRead.model_validate(user),
        usage=UsageRead(
            watchers_used=usage.watchers,
            watchers_limit=limit.max_watchers,
            subreddits_used=usage.subreddits,
            subreddits_limit=limit.max_subreddits,
        ),
        unread_matches=unread,
    )


# Permanently delete the caller's account: cancels billing, deletes the Clerk identity, and
# removes every row of theirs (watchers, matches, notification channels, subscription history).
@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> None:
    await delete_account(session, settings, user)
