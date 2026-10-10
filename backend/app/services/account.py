"""Full account deletion.

Cancels any Stripe subscription, deletes the Clerk identity, then deletes the local `users` row.
Every other table (`subscriptions`, `watchers` — and `matches` through it — and
`notification_channels`) has `ondelete="CASCADE"` back to `users.id`, so the DB delete is the one
step that needs to clean up everything else.
"""

from __future__ import annotations

import logging

import stripe
from clerk_backend_api import Clerk
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.user import User
from app.services.billing import get_subscription

logger = logging.getLogger(__name__)


async def _cancel_subscription(session: AsyncSession, settings: Settings, user: User) -> None:
    if not settings.STRIPE_SECRET_KEY:
        return
    subscription = await get_subscription(session, user.id)
    if subscription is None or subscription.status == "canceled":
        return
    try:
        await stripe.Subscription.cancel_async(
            subscription.stripe_subscription_id, api_key=settings.STRIPE_SECRET_KEY
        )
    except stripe.StripeError as error:
        # Already canceled or gone on Stripe's side isn't a reason to block deleting the account.
        logger.warning("account: stripe cancel failed for user %s (%s)", user.id, error)


async def _delete_clerk_user(settings: Settings, user: User) -> None:
    if not settings.CLERK_SECRET_KEY:
        return
    async with Clerk(bearer_auth=settings.CLERK_SECRET_KEY) as clerk:
        try:
            await clerk.users.delete_async(user_id=user.clerk_user_id)
        except Exception as error:  # noqa: BLE001 - Clerk's SDK raises its own error hierarchy
            logger.warning("account: clerk delete failed for user %s (%s)", user.id, error)


# Delete a user's account everywhere it exists. Order matters: Stripe and Clerk still have
# `user.id`/`user.clerk_user_id` to work with here, so those calls run first — the local delete
# goes last since it's the one step that can't fail partway.
async def delete_account(session: AsyncSession, settings: Settings, user: User) -> None:
    await _cancel_subscription(session, settings, user)
    await _delete_clerk_user(settings, user)
    await session.delete(user)
    await session.commit()
