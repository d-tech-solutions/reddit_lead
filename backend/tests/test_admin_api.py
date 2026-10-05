"""Superadmin endpoints: access control, listing, plan/active changes, deletion.

Same fixture pattern as `test_account_api.py` — `auth_client`/`db_user` for a regular account,
`admin_client`/`db_admin_user` for the staff one, both sharing the test's rolled-back transaction.
"""

from __future__ import annotations

import pytest

from app.models.user import User
from app.models.watcher import Watcher


@pytest.mark.db
async def test_non_admin_is_refused_on_every_admin_route(auth_client, db_user):
    responses = [
        await auth_client.get("/api/v1/admin/users"),
        await auth_client.get(f"/api/v1/admin/users/{db_user.id}"),
        await auth_client.patch(f"/api/v1/admin/users/{db_user.id}", json={"plan": "standard"}),
        await auth_client.delete(f"/api/v1/admin/users/{db_user.id}"),
    ]
    assert all(response.status_code == 403 for response in responses)


@pytest.mark.db
async def test_list_users_includes_watcher_count(admin_client, db_admin_user, db_session, db_user):
    db_session.add(Watcher(user_id=db_user.id, name="w", intent_text="x", subreddits=["forhire"]))
    await db_session.commit()

    response = await admin_client.get("/api/v1/admin/users")

    assert response.status_code == 200
    by_id = {row["id"]: row for row in response.json()}
    assert by_id[str(db_user.id)]["watcher_count"] == 1
    assert by_id[str(db_admin_user.id)]["watcher_count"] == 0


@pytest.mark.db
async def test_get_user_detail_includes_their_watchers(admin_client, db_session, db_user):
    watcher = Watcher(user_id=db_user.id, name="w", intent_text="x", subreddits=["forhire"])
    db_session.add(watcher)
    await db_session.commit()

    response = await admin_client.get(f"/api/v1/admin/users/{db_user.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["watcher_count"] == 1
    assert [w["id"] for w in body["watchers"]] == [str(watcher.id)]


@pytest.mark.db
async def test_get_user_detail_404s_for_an_unknown_id(admin_client):
    response = await admin_client.get("/api/v1/admin/users/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.db
async def test_patch_plan_updates_it(admin_client, db_user):
    response = await admin_client.patch(
        f"/api/v1/admin/users/{db_user.id}", json={"plan": "standard"}
    )
    assert response.status_code == 200
    assert response.json()["plan"] == "standard"


@pytest.mark.db
async def test_patch_unknown_plan_is_400(admin_client, db_user):
    response = await admin_client.patch(
        f"/api/v1/admin/users/{db_user.id}", json={"plan": "platinum"}
    )
    assert response.status_code == 400


@pytest.mark.db
async def test_deactivating_pauses_every_watcher(admin_client, db_session, db_user):
    watcher = Watcher(user_id=db_user.id, name="w", intent_text="x", subreddits=["forhire"])
    db_session.add(watcher)
    await db_session.commit()

    response = await admin_client.patch(
        f"/api/v1/admin/users/{db_user.id}", json={"is_active": False}
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # `session.get()` after `expire_all()` would trust the identity map and defer the attribute
    # reload to plain attribute access, which `AsyncSession` can't do implicitly — an explicit
    # `refresh()` is the awaitable way to repopulate an already-tracked object's stale attributes.
    await db_session.refresh(watcher)
    assert watcher.status == "paused"


@pytest.mark.db
async def test_reactivating_does_not_resume_watchers(admin_client, db_session, db_user):
    watcher = Watcher(
        user_id=db_user.id, name="w", intent_text="x", subreddits=["forhire"], status="paused"
    )
    db_session.add(watcher)
    await db_session.commit()

    await admin_client.patch(f"/api/v1/admin/users/{db_user.id}", json={"is_active": False})
    response = await admin_client.patch(
        f"/api/v1/admin/users/{db_user.id}", json={"is_active": True}
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is True

    await db_session.refresh(watcher)
    assert watcher.status == "paused"


@pytest.mark.db
async def test_deactivated_user_gets_403_from_get_current_user(db_session, monkeypatch):
    from fastapi import HTTPException

    from app.api import deps

    user = User(clerk_user_id="user_deactivated", email="d@example.com", is_active=False)
    db_session.add(user)
    await db_session.commit()

    async def fake_verify(token, settings):
        return {"sub": "user_deactivated"}

    monkeypatch.setattr(deps, "verify_clerk_token", fake_verify)

    class FakeRequest:
        def __init__(self):
            self.headers = {"authorization": "Bearer tok"}

    with pytest.raises(HTTPException) as error:
        await deps.get_current_user(FakeRequest(), session=db_session, settings=object())

    assert error.value.status_code == 403


@pytest.mark.db
async def test_admin_cannot_deactivate_or_delete_themselves(admin_client, db_admin_user):
    responses = [
        await admin_client.patch(
            f"/api/v1/admin/users/{db_admin_user.id}", json={"is_active": False}
        ),
        await admin_client.delete(f"/api/v1/admin/users/{db_admin_user.id}"),
    ]
    assert all(response.status_code == 400 for response in responses)


@pytest.mark.db
async def test_delete_user_endpoint_calls_delete_account(admin_client, db_user, monkeypatch):
    # `delete_account`'s own Stripe-cancel/Clerk-delete/cascade behavior is already proven in
    # test_account_api.py against a `FakeSettings`; going through the real endpoint here would
    # instead resolve the real `get_settings()` and could make live Clerk/Stripe calls with
    # whatever secrets happen to be configured in the environment running the tests. Monkeypatching
    # it here, same as `test_delete_me_endpoint_calls_delete_account` does for `/me`, checks only
    # what this endpoint is responsible for: routing the *right* target user into that call.
    from app.api.v1.endpoints import admin as admin_endpoint

    calls = []

    async def fake_delete_account(session, settings, user):
        calls.append(user.id)

    monkeypatch.setattr(admin_endpoint, "delete_account", fake_delete_account)

    response = await admin_client.delete(f"/api/v1/admin/users/{db_user.id}")

    assert response.status_code == 204
    assert calls == [db_user.id]
