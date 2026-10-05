"""Billing: pure service-layer logic (no network, no DB) plus a few `db`-marked tests for the
webhook's database side effects and the HTTP layer.

Stripe itself is never called — `stripe.checkout.Session.create_async` /
`stripe.billing_portal.Session.create_async` / `stripe.Webhook.construct_event` are monkeypatched,
same pattern `test_auth.py` uses for Clerk's `verify_token_async`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest
import stripe
from sqlalchemy import select

from app.api.v1.endpoints import billing as billing_endpoint
from app.models.subscription import Subscription
from app.services import billing as billing_service
from app.services.billing import BillingError, get_subscription, handle_webhook_event, list_plans


@dataclass
class FakeSettings:
    STRIPE_SECRET_KEY: str = "sk_test"
    STRIPE_WEBHOOK_SECRET: str = "whsec_test"
    STRIPE_PRICE_STANDARD: str = "price_standard"
    STRIPE_PRICE_PREMIUM: str = "price_premium"
    STRIPE_PRICE_ENTERPRISE: str = "price_enterprise"
    FRONTEND_URL: str = "http://localhost:3000"


def checkout_completed_event(*, user_id: uuid.UUID, plan: str) -> dict:
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "subscription",
                "client_reference_id": str(user_id),
                "customer": "cus_123",
                "subscription": "sub_123",
                "metadata": {"plan": plan},
            }
        },
    }


def subscription_updated_event(
    *, user_id: uuid.UUID, price_id: str, status: str = "active", cancel_at_period_end: bool = False
) -> dict:
    return {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_123",
                "status": status,
                "current_period_end": 1_800_000_000,
                "cancel_at_period_end": cancel_at_period_end,
                "metadata": {"user_id": str(user_id)},
                "items": {"data": [{"price": {"id": price_id}}]},
            }
        },
    }


def subscription_deleted_event(*, user_id: uuid.UUID) -> dict:
    return {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_123", "customer": "cus_123", "metadata": {"user_id": str(user_id)}}},
    }


# --- Pure logic: no DB, no network -------------------------------------------------------------


def test_list_plans_matches_the_tier_table():
    plans = {plan.id: plan for plan in list_plans()}
    assert set(plans) == {"free", "standard", "premium", "enterprise"}
    assert plans["free"].price_cents == 0
    assert plans["standard"].price_cents == 900
    assert plans["premium"].price_cents == 2900
    assert plans["enterprise"].price_cents == 4900
    # Enterprise is capped, not unbounded, now that it's self-serve.
    assert plans["enterprise"].max_watchers == 25
    assert plans["enterprise"].max_subreddits == 150


async def test_checkout_requires_stripe_secret_key():
    settings = FakeSettings(STRIPE_SECRET_KEY="")
    with pytest.raises(BillingError, match="not configured"):
        await billing_service.create_checkout_session(None, settings, _fake_user(), "standard")


async def test_checkout_requires_a_configured_price():
    settings = FakeSettings(STRIPE_PRICE_STANDARD="")
    with pytest.raises(BillingError, match="No Stripe price"):
        await billing_service.create_checkout_session(None, settings, _fake_user(), "standard")


async def test_portal_requires_stripe_secret_key():
    settings = FakeSettings(STRIPE_SECRET_KEY="")
    with pytest.raises(BillingError, match="not configured"):
        await billing_service.create_portal_session(None, settings, _fake_user())


def test_verify_webhook_signature_requires_a_configured_secret():
    settings = FakeSettings(STRIPE_WEBHOOK_SECRET="")
    with pytest.raises(BillingError, match="not configured"):
        billing_service.verify_webhook_signature(settings, b"{}", "sig")


def test_verify_webhook_signature_rejects_a_bad_signature(monkeypatch):
    def boom(payload, sig_header, secret):
        raise stripe.StripeError("bad sig")

    monkeypatch.setattr(stripe.Webhook, "construct_event", boom)

    with pytest.raises(BillingError, match="Invalid webhook signature"):
        billing_service.verify_webhook_signature(FakeSettings(), b"{}", "sig")


async def test_unknown_event_types_are_ignored():
    # No session/settings work should happen for an event type we don't handle — passing `None`
    # for both would blow up if the dispatcher tried to use them.
    await handle_webhook_event(None, None, {"type": "invoice.payment_failed", "data": {"object": {}}})


def _fake_user():
    @dataclass
    class _User:
        id: uuid.UUID = field(default_factory=uuid.uuid4)
        email: str | None = "t@example.com"

    return _User()


# --- Webhook database side effects (needs Postgres) ---------------------------------------------


@pytest.mark.db
async def test_checkout_completed_creates_subscription_and_sets_plan(db_session, db_user):
    event = checkout_completed_event(user_id=db_user.id, plan="standard")

    await handle_webhook_event(db_session, FakeSettings(), event)

    await db_session.refresh(db_user)
    assert db_user.plan == "standard"

    subscription = await get_subscription(db_session, db_user.id)
    assert subscription is not None
    assert subscription.stripe_customer_id == "cus_123"
    assert subscription.stripe_subscription_id == "sub_123"
    assert subscription.status == "active"


@pytest.mark.db
async def test_subscription_updated_resolves_plan_from_price_id(db_session, db_user):
    settings = FakeSettings()
    await handle_webhook_event(
        db_session, settings, checkout_completed_event(user_id=db_user.id, plan="standard")
    )

    # A portal-driven upgrade changes the price on the subscription but doesn't necessarily touch
    # metadata — the handler must resolve the new plan from the price id, not stale metadata.
    await handle_webhook_event(
        db_session,
        settings,
        subscription_updated_event(user_id=db_user.id, price_id=settings.STRIPE_PRICE_PREMIUM),
    )

    await db_session.refresh(db_user)
    assert db_user.plan == "premium"

    subscription = await get_subscription(db_session, db_user.id)
    assert subscription.current_period_end is not None
    assert subscription.status == "active"


@pytest.mark.db
async def test_subscription_updated_with_unrecognised_price_is_ignored(db_session, db_user):
    await handle_webhook_event(
        db_session,
        FakeSettings(),
        subscription_updated_event(user_id=db_user.id, price_id="price_unknown"),
    )

    await db_session.refresh(db_user)
    assert db_user.plan == "free"
    assert await get_subscription(db_session, db_user.id) is None


@pytest.mark.db
async def test_subscription_deleted_resets_to_free(db_session, db_user):
    settings = FakeSettings()
    await handle_webhook_event(
        db_session, settings, checkout_completed_event(user_id=db_user.id, plan="premium")
    )

    await handle_webhook_event(db_session, settings, subscription_deleted_event(user_id=db_user.id))

    await db_session.refresh(db_user)
    assert db_user.plan == "free"

    subscription = await get_subscription(db_session, db_user.id)
    assert subscription.status == "canceled"


@pytest.mark.db
async def test_resubscribing_updates_the_same_row_not_a_second_one(db_session, db_user):
    settings = FakeSettings()
    await handle_webhook_event(
        db_session, settings, checkout_completed_event(user_id=db_user.id, plan="standard")
    )
    await handle_webhook_event(db_session, settings, subscription_deleted_event(user_id=db_user.id))

    # Re-subscribing gets a new Stripe subscription id.
    second_event = checkout_completed_event(user_id=db_user.id, plan="premium")
    second_event["data"]["object"]["subscription"] = "sub_456"
    await handle_webhook_event(db_session, settings, second_event)

    result = await db_session.execute(select(Subscription).where(Subscription.user_id == db_user.id))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].stripe_subscription_id == "sub_456"
    assert rows[0].plan == "premium"


# --- HTTP layer ----------------------------------------------------------------------------------


async def test_plans_endpoint_lists_all_tiers(client):
    response = await client.get("/api/v1/billing/plans")
    assert response.status_code == 200
    ids = {plan["id"] for plan in response.json()}
    assert ids == {"free", "standard", "premium", "enterprise"}


@pytest.mark.db
async def test_checkout_endpoint_rejects_an_unknown_plan(auth_client):
    response = await auth_client.post("/api/v1/billing/checkout", json={"plan": "gold"})
    assert response.status_code == 422


@pytest.mark.db
async def test_checkout_endpoint_returns_the_stripe_url(auth_client, monkeypatch):
    async def fake_create_checkout_session(session, settings, user, plan):
        return f"https://checkout.stripe.com/{plan}"

    monkeypatch.setattr(
        billing_endpoint, "create_checkout_session", fake_create_checkout_session
    )

    response = await auth_client.post("/api/v1/billing/checkout", json={"plan": "premium"})
    assert response.status_code == 200
    assert response.json()["url"] == "https://checkout.stripe.com/premium"


@pytest.mark.db
async def test_checkout_endpoint_translates_billing_error_to_400(auth_client, monkeypatch):
    async def fake_create_checkout_session(session, settings, user, plan):
        raise BillingError("No Stripe price is configured for the 'premium' plan.")

    monkeypatch.setattr(
        billing_endpoint, "create_checkout_session", fake_create_checkout_session
    )

    response = await auth_client.post("/api/v1/billing/checkout", json={"plan": "premium"})
    assert response.status_code == 400
    assert "premium" in response.json()["detail"]


@pytest.mark.db
async def test_portal_endpoint_returns_the_stripe_url(auth_client, monkeypatch):
    async def fake_create_portal_session(session, settings, user):
        return "https://billing.stripe.com/session"

    monkeypatch.setattr(billing_endpoint, "create_portal_session", fake_create_portal_session)

    response = await auth_client.post("/api/v1/billing/portal")
    assert response.status_code == 200
    assert response.json()["url"] == "https://billing.stripe.com/session"


@pytest.mark.db
async def test_billing_endpoint_defaults_to_free_with_no_subscription(auth_client, db_user):
    response = await auth_client.get("/api/v1/billing")
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == db_user.plan == "free"
    assert body["status"] is None
    assert body["cancel_at_period_end"] is False


async def test_webhook_endpoint_rejects_an_invalid_signature(client, monkeypatch):
    def fake_verify(settings, payload, sig_header):
        raise BillingError("Invalid webhook signature.")

    monkeypatch.setattr(billing_endpoint, "verify_webhook_signature", fake_verify)

    response = await client.post(
        "/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "bad"}
    )
    assert response.status_code == 400


async def test_webhook_endpoint_accepts_a_valid_signature(client, monkeypatch):
    fake_event = {"type": "invoice.payment_failed", "data": {"object": {}}}

    def fake_verify(settings, payload, sig_header):
        return fake_event

    calls = []

    async def fake_handle(session, settings, event):
        calls.append(event)

    monkeypatch.setattr(billing_endpoint, "verify_webhook_signature", fake_verify)
    monkeypatch.setattr(billing_endpoint, "handle_webhook_event", fake_handle)

    response = await client.post(
        "/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "good"}
    )
    assert response.status_code == 200
    assert response.json() == {"received": True}
    assert calls == [fake_event]
