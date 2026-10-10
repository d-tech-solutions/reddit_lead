"""Account deletion: the service's Stripe-cancel + DB-cascade behavior, and the HTTP layer.

Stripe is monkeypatched, same pattern as `test_billing_api.py`. Clerk deletion is skipped by
leaving `CLERK_SECRET_KEY` unset on `FakeSettings` (the service treats that as "no Clerk identity
to clean up"), so these tests never touch the Clerk SDK.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
import stripe

from app.api.v1.endpoints import users as users_endpoint
from app.models.subscription import Subscription
from app.models.user import User
from app.models.watcher import Watcher
from app.services.account import delete_account


@dataclass
class FakeSettings:
    STRIPE_SECRET_KEY: str = ""
    CLERK_SECRET_KEY: str = ""


@pytest.mark.db
async def test_delete_account_removes_the_user_and_cascades(db_session, db_user):
    watcher = Watcher(
        user_id=db_user.id, name="w", intent_text="x", subreddits=["test"]
    )
    db_session.add(watcher)
    await db_session.commit()
    # Captured before the cascade expires the object — reading an expired attribute needs a
    # (synchronous-looking) reload that an already-expired ORM object can't do outside `await`.
    watcher_id, user_id = watcher.id, db_user.id

    await delete_account(db_session, FakeSettings(), db_user)

    # The cascade happens in Postgres, not through SQLAlchemy, so the session's identity map
    # doesn't know about it yet — `expire_all` forces the next `get` to hit the database.
    db_session.expire_all()
    assert await db_session.get(User, user_id) is None
    assert await db_session.get(Watcher, watcher_id) is None


@pytest.mark.db
async def test_delete_account_cancels_an_active_stripe_subscription(db_session, db_user, monkeypatch):
    subscription = Subscription(
        user_id=db_user.id,
        stripe_customer_id="cus_1",
        stripe_subscription_id="sub_1",
        plan="standard",
        status="active",
    )
    db_session.add(subscription)
    await db_session.commit()

    cancelled = []

    async def fake_cancel(subscription_id, **kwargs):
        cancelled.append(subscription_id)

    monkeypatch.setattr(stripe.Subscription, "cancel_async", fake_cancel)

    await delete_account(db_session, FakeSettings(STRIPE_SECRET_KEY="sk_test"), db_user)

    assert cancelled == ["sub_1"]
    assert await db_session.get(User, db_user.id) is None


@pytest.mark.db
async def test_delete_account_ignores_an_already_cancelled_subscription(db_session, db_user, monkeypatch):
    subscription = Subscription(
        user_id=db_user.id,
        stripe_customer_id="cus_1",
        stripe_subscription_id="sub_1",
        plan="standard",
        status="canceled",
    )
    db_session.add(subscription)
    await db_session.commit()

    def boom(*args, **kwargs):
        raise AssertionError("should not call Stripe for an already-cancelled subscription")

    monkeypatch.setattr(stripe.Subscription, "cancel_async", boom)

    await delete_account(db_session, FakeSettings(STRIPE_SECRET_KEY="sk_test"), db_user)

    assert await db_session.get(User, db_user.id) is None


@pytest.mark.db
async def test_delete_me_endpoint_calls_delete_account(auth_client, db_user, monkeypatch):
    calls = []

    async def fake_delete_account(session, settings, user):
        calls.append(user.id)

    monkeypatch.setattr(users_endpoint, "delete_account", fake_delete_account)

    response = await auth_client.delete("/api/v1/me")

    assert response.status_code == 204
    assert calls == [db_user.id]
