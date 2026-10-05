"""Stripe checkout/portal session creation and webhook-driven subscription sync.

The user's `plan` column stays the fast, always-current field the rest of the app reads
(limits.py, /me); this module's job is keeping it in sync with Stripe and maintaining the
`subscriptions` detail row. Every subscription-carrying webhook event is trusted to identify the
user via the `user_id` metadata set on the subscription at checkout time (`subscription_data`
below), not via a customer-id lookup — that metadata survives portal-driven plan changes, so it
stays reliable for the life of the subscription.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.constants import DEFAULT_PLAN, TIER_LIMITS
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.billing import PlanRead

logger = logging.getLogger(__name__)


class BillingError(Exception):
    """Raised for a request that can't become (or come from) a valid Stripe call — an unknown or
    unconfigured plan, a missing billing account, a bad webhook signature. Carries a message the
    endpoint layer turns into an HTTP response."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def list_plans() -> list[PlanRead]:
    return [
        PlanRead(
            id=plan_id,
            price_cents=limit.monthly_price_cents,
            max_watchers=limit.max_watchers,
            max_subreddits=limit.max_subreddits,
        )
        for plan_id, limit in TIER_LIMITS.items()
    ]


def _configured_price_ids(settings: Settings) -> dict[str, str]:
    ids = {
        "standard": settings.STRIPE_PRICE_STANDARD,
        "premium": settings.STRIPE_PRICE_PREMIUM,
        "enterprise": settings.STRIPE_PRICE_ENTERPRISE,
    }
    return {plan: price_id for plan, price_id in ids.items() if price_id}


def _price_id_for_plan(settings: Settings, plan: str) -> str:
    price_id = _configured_price_ids(settings).get(plan)
    if not price_id:
        raise BillingError(f"No Stripe price is configured for the '{plan}' plan.")
    return price_id


def _plan_for_price_id(settings: Settings, price_id: str) -> str | None:
    for plan, configured_id in _configured_price_ids(settings).items():
        if configured_id == price_id:
            return plan
    return None


async def get_subscription(session: AsyncSession, user_id: uuid.UUID) -> Subscription | None:
    result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
    return result.scalar_one_or_none()


# Start a Checkout session for a paid plan.
#
# Reuses the existing Stripe customer if the user has subscribed before, so a re-subscribe or plan
# change doesn't create a second customer object for the same person.
async def create_checkout_session(
    session: AsyncSession, settings: Settings, user: User, plan: str
) -> str:
    if not settings.STRIPE_SECRET_KEY:
        raise BillingError("Billing is not configured on this server.")
    price_id = _price_id_for_plan(settings, plan)
    existing = await get_subscription(session, user.id)

    customer_kwargs: dict[str, Any] = {}
    if existing is not None and existing.stripe_customer_id:
        customer_kwargs["customer"] = existing.stripe_customer_id
    elif user.email:
        customer_kwargs["customer_email"] = user.email

    checkout_session = await stripe.checkout.Session.create_async(
        api_key=settings.STRIPE_SECRET_KEY,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        client_reference_id=str(user.id),
        metadata={"plan": plan},
        subscription_data={"metadata": {"user_id": str(user.id), "plan": plan}},
        success_url=f"{settings.FRONTEND_URL}/billing?checkout=success",
        cancel_url=f"{settings.FRONTEND_URL}/billing?checkout=cancelled",
        **customer_kwargs,
    )
    if not checkout_session.url:
        raise BillingError("Stripe did not return a checkout URL.")
    return checkout_session.url


# Start a Billing Portal session so the user can update their card, switch plans, or cancel
# without us building any of that UI ourselves.
async def create_portal_session(session: AsyncSession, settings: Settings, user: User) -> str:
    if not settings.STRIPE_SECRET_KEY:
        raise BillingError("Billing is not configured on this server.")
    existing = await get_subscription(session, user.id)
    if existing is None or not existing.stripe_customer_id:
        raise BillingError("Subscribe to a paid plan before managing billing.")

    portal_session = await stripe.billing_portal.Session.create_async(
        api_key=settings.STRIPE_SECRET_KEY,
        customer=existing.stripe_customer_id,
        return_url=f"{settings.FRONTEND_URL}/billing",
    )
    return portal_session.url


def verify_webhook_signature(settings: Settings, payload: bytes, sig_header: str) -> stripe.Event:
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise BillingError("Webhook secret is not configured on this server.")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    # `ValueError` covers an unparseable payload; `StripeError` (the base every Stripe SDK
    # exception derives from, including `SignatureVerificationError`) covers a bad signature.
    except (ValueError, stripe.StripeError) as error:
        raise BillingError("Invalid webhook signature.") from error


# Upsert the caller's `subscriptions` row and mirror the plan onto `users.plan` in one commit, so
# the two never observably disagree between requests.
async def _apply_subscription_state(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    plan: str,
    status: str,
    current_period_end: datetime | None,
    cancel_at_period_end: bool,
) -> None:
    row = await get_subscription(session, user_id)
    if row is None:
        row = Subscription(user_id=user_id)
        session.add(row)

    row.stripe_customer_id = stripe_customer_id
    row.stripe_subscription_id = stripe_subscription_id
    row.plan = plan
    row.status = status
    row.current_period_end = current_period_end
    row.cancel_at_period_end = cancel_at_period_end

    user = await session.get(User, user_id)
    if user is not None:
        user.plan = plan

    await session.commit()


async def _handle_checkout_completed(
    session: AsyncSession, settings: Settings, obj: dict[str, Any]
) -> None:
    if obj.get("mode") != "subscription":
        return

    user_id_raw = obj.get("client_reference_id")
    customer_id = obj.get("customer")
    subscription_id = obj.get("subscription")
    plan = (obj.get("metadata") or {}).get("plan")
    if not (user_id_raw and customer_id and subscription_id and plan):
        logger.warning("billing: checkout.session.completed missing required fields")
        return

    # `current_period_end` isn't on the Checkout Session — the `customer.subscription.updated`
    # event Stripe fires around the same time fills it in moments later.
    await _apply_subscription_state(
        session,
        user_id=uuid.UUID(user_id_raw),
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        plan=plan,
        status="active",
        current_period_end=None,
        cancel_at_period_end=False,
    )


async def _handle_subscription_updated(
    session: AsyncSession, settings: Settings, obj: dict[str, Any]
) -> None:
    user_id_raw = (obj.get("metadata") or {}).get("user_id")
    if not user_id_raw:
        logger.warning("billing: subscription.updated missing user_id metadata")
        return

    items = (obj.get("items") or {}).get("data") or []
    price_id = items[0]["price"]["id"] if items else None
    # Read the plan back from the price id rather than trusting stale metadata — this is what
    # makes a portal-driven upgrade/downgrade (which changes the price but not the metadata) sync
    # correctly.
    plan = _plan_for_price_id(settings, price_id) if price_id else None
    if plan is None:
        logger.warning("billing: subscription.updated with unrecognised price %s", price_id)
        return

    period_end_ts = obj.get("current_period_end")
    current_period_end = (
        datetime.fromtimestamp(period_end_ts, tz=UTC) if period_end_ts else None
    )

    await _apply_subscription_state(
        session,
        user_id=uuid.UUID(user_id_raw),
        stripe_customer_id=obj.get("customer", ""),
        stripe_subscription_id=obj.get("id", ""),
        plan=plan,
        status=obj.get("status", "active"),
        current_period_end=current_period_end,
        cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
    )


async def _handle_subscription_deleted(
    session: AsyncSession, settings: Settings, obj: dict[str, Any]
) -> None:
    user_id_raw = (obj.get("metadata") or {}).get("user_id")
    if not user_id_raw:
        logger.warning("billing: subscription.deleted missing user_id metadata")
        return
    user_id = uuid.UUID(user_id_raw)

    row = await get_subscription(session, user_id)
    if row is not None:
        row.status = "canceled"
        row.cancel_at_period_end = False

    # Falls back to the free tier rather than deleting the row: `subscriptions` is a history of
    # the billing relationship, and enforce_limits() already handles "over the new plan's limit"
    # by blocking further growth, not by touching existing watchers.
    user = await session.get(User, user_id)
    if user is not None:
        user.plan = DEFAULT_PLAN

    await session.commit()


_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
}


# Dispatch a verified Stripe event. Unhandled event types are ignored rather than rejected — Stripe
# expects a 200 for any event type it might ever send, not just the ones we act on.
async def handle_webhook_event(
    session: AsyncSession, settings: Settings, event: stripe.Event
) -> None:
    handler = _HANDLERS.get(event["type"])
    if handler is None:
        return
    await handler(session, settings, event["data"]["object"])
