"""Endpoint tests against a real Postgres.

Marked `db` and skipped automatically when Postgres is unreachable — see tests/conftest.py.
Everything runs inside a transaction that is rolled back, so these are safe against a shared
development database.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.user import User
from app.models.watcher import Watcher

pytestmark = pytest.mark.db

VALID_INTENT = "someone looking to hire a developer for a web project"


def payload(**overrides) -> dict:
    body = {
        "name": "dev hiring",
        "intent_text": VALID_INTENT,
        "subreddits": ["forhire"],
    }
    body.update(overrides)
    return body


async def test_create_returns_the_watcher(auth_client):
    response = await auth_client.post("/api/v1/watchers", json=payload())

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "dev hiring"
    assert body["subreddits"] == ["forhire"]
    assert body["direction"] == "requesting"
    assert body["embedded_at"] is None


async def test_create_never_leaks_the_embedding(auth_client):
    response = await auth_client.post("/api/v1/watchers", json=payload())
    assert "intent_embedding" not in response.json()


async def test_created_watcher_is_owned_by_the_caller(auth_client, db_session, db_user):
    response = await auth_client.post("/api/v1/watchers", json=payload())

    watcher = await db_session.get(Watcher, uuid.UUID(response.json()["id"]))
    assert watcher.user_id == db_user.id


async def test_create_normalises_subreddits(auth_client):
    response = await auth_client.post(
        "/api/v1/watchers", json=payload(subreddits=["r/ForHire", "/r/SlaveLabour"])
    )
    assert response.json()["subreddits"] == ["forhire", "slavelabour"]


async def test_create_rejects_a_short_intent(auth_client):
    response = await auth_client.post("/api/v1/watchers", json=payload(intent_text="devs"))
    assert response.status_code == 422


async def test_create_rejects_an_invalid_subreddit(auth_client):
    response = await auth_client.post("/api/v1/watchers", json=payload(subreddits=["not valid!"]))
    assert response.status_code == 422


async def test_second_watcher_hits_the_free_tier_limit(auth_client):
    first = await auth_client.post("/api/v1/watchers", json=payload())
    assert first.status_code == 201

    second = await auth_client.post("/api/v1/watchers", json=payload(name="another"))

    assert second.status_code == 409
    assert "1 watcher" in second.json()["detail"]


async def test_too_many_subreddits_hits_the_pool_limit(auth_client):
    response = await auth_client.post(
        "/api/v1/watchers", json=payload(subreddits=["forhire", "slavelabour", "jobs", "hiring"])
    )

    assert response.status_code == 409
    assert "3 subreddits" in response.json()["detail"]


async def test_list_returns_only_the_callers_watchers(auth_client, db_session, db_user):
    await auth_client.post("/api/v1/watchers", json=payload())

    stranger = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:8]}")
    db_session.add(stranger)
    await db_session.commit()
    db_session.add(
        Watcher(
            user_id=stranger.id,
            name="not yours",
            intent_text=VALID_INTENT,
            subreddits=["forhire"],
        )
    )
    await db_session.commit()

    response = await auth_client.get("/api/v1/watchers")

    assert response.status_code == 200
    names = [w["name"] for w in response.json()]
    assert names == ["dev hiring"]


async def test_get_someone_elses_watcher_is_404_not_403(auth_client, db_session):
    # A 403 would confirm the id exists, which lets an attacker enumerate other users' watchers.
    stranger = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:8]}")
    db_session.add(stranger)
    await db_session.commit()
    watcher = Watcher(
        user_id=stranger.id, name="theirs", intent_text=VALID_INTENT, subreddits=["forhire"]
    )
    db_session.add(watcher)
    await db_session.commit()

    response = await auth_client.get(f"/api/v1/watchers/{watcher.id}")
    assert response.status_code == 404


async def test_get_a_missing_watcher_is_404(auth_client):
    response = await auth_client.get(f"/api/v1/watchers/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_patch_updates_only_what_was_sent(auth_client):
    created = (await auth_client.post("/api/v1/watchers", json=payload())).json()

    response = await auth_client.patch(
        f"/api/v1/watchers/{created['id']}", json={"name": "renamed"}
    )

    body = response.json()
    assert body["name"] == "renamed"
    assert body["intent_text"] == VALID_INTENT
    assert body["subreddits"] == ["forhire"]


async def test_patch_can_pause_a_watcher(auth_client):
    created = (await auth_client.post("/api/v1/watchers", json=payload())).json()

    response = await auth_client.patch(
        f"/api/v1/watchers/{created['id']}", json={"status": "paused"}
    )
    assert response.json()["status"] == "paused"


async def test_changing_the_intent_clears_the_embedding(auth_client, db_session):
    created = (await auth_client.post("/api/v1/watchers", json=payload())).json()
    watcher_id = uuid.UUID(created["id"])

    # Pretend the embedding worker has already run.
    watcher = await db_session.get(Watcher, watcher_id)
    watcher.intent_embedding = [0.1] * 1536
    from datetime import UTC, datetime

    watcher.embedded_at = datetime.now(UTC)
    await db_session.commit()

    await auth_client.patch(
        f"/api/v1/watchers/{watcher_id}",
        json={"intent_text": "people who need a logo designed for a startup"},
    )

    await db_session.refresh(watcher)
    # The stale vector must go, or the matcher keeps comparing posts to the old wording.
    assert watcher.intent_embedding is None
    assert watcher.embedded_at is None


async def test_renaming_does_not_clear_the_embedding(auth_client, db_session):
    created = (await auth_client.post("/api/v1/watchers", json=payload())).json()
    watcher = await db_session.get(Watcher, uuid.UUID(created["id"]))
    watcher.intent_embedding = [0.1] * 1536
    await db_session.commit()

    await auth_client.patch(f"/api/v1/watchers/{created['id']}", json={"name": "new name"})

    await db_session.refresh(watcher)
    # Only the intent text feeds the vector — re-embedding on a rename would be wasted spend.
    assert watcher.intent_embedding is not None


async def test_resending_the_same_intent_does_not_clear_the_embedding(auth_client, db_session):
    created = (await auth_client.post("/api/v1/watchers", json=payload())).json()
    watcher = await db_session.get(Watcher, uuid.UUID(created["id"]))
    watcher.intent_embedding = [0.1] * 1536
    await db_session.commit()

    await auth_client.patch(
        f"/api/v1/watchers/{created['id']}", json={"intent_text": VALID_INTENT}
    )

    await db_session.refresh(watcher)
    assert watcher.intent_embedding is not None


async def test_patch_lets_a_capped_user_edit_their_watcher(auth_client):
    # The user is at their 1-watcher cap; editing must not be mistaken for creating another.
    created = (await auth_client.post("/api/v1/watchers", json=payload())).json()

    response = await auth_client.patch(
        f"/api/v1/watchers/{created['id']}", json={"subreddits": ["slavelabour", "jobs"]}
    )

    assert response.status_code == 200
    assert response.json()["subreddits"] == ["slavelabour", "jobs"]


async def test_patch_still_enforces_the_subreddit_pool(auth_client):
    created = (await auth_client.post("/api/v1/watchers", json=payload())).json()

    response = await auth_client.patch(
        f"/api/v1/watchers/{created['id']}",
        json={"subreddits": ["a_sub", "b_sub", "c_sub", "d_sub"]},
    )
    assert response.status_code == 409


async def test_patch_someone_elses_watcher_is_404(auth_client, db_session):
    stranger = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:8]}")
    db_session.add(stranger)
    await db_session.commit()
    watcher = Watcher(
        user_id=stranger.id, name="theirs", intent_text=VALID_INTENT, subreddits=["forhire"]
    )
    db_session.add(watcher)
    await db_session.commit()

    response = await auth_client.patch(f"/api/v1/watchers/{watcher.id}", json={"name": "mine now"})
    assert response.status_code == 404


async def test_delete_removes_the_watcher(auth_client, db_session):
    created = (await auth_client.post("/api/v1/watchers", json=payload())).json()

    response = await auth_client.delete(f"/api/v1/watchers/{created['id']}")

    assert response.status_code == 204
    assert await db_session.get(Watcher, uuid.UUID(created["id"])) is None


async def test_delete_frees_the_quota(auth_client):
    created = (await auth_client.post("/api/v1/watchers", json=payload())).json()
    await auth_client.delete(f"/api/v1/watchers/{created['id']}")

    response = await auth_client.post("/api/v1/watchers", json=payload(name="replacement"))
    assert response.status_code == 201


async def test_delete_someone_elses_watcher_is_404(auth_client, db_session):
    stranger = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:8]}")
    db_session.add(stranger)
    await db_session.commit()
    watcher = Watcher(
        user_id=stranger.id, name="theirs", intent_text=VALID_INTENT, subreddits=["forhire"]
    )
    db_session.add(watcher)
    await db_session.commit()

    response = await auth_client.delete(f"/api/v1/watchers/{watcher.id}")
    assert response.status_code == 404

    remaining = await db_session.execute(select(Watcher).where(Watcher.id == watcher.id))
    assert remaining.scalar_one_or_none() is not None


async def test_me_reports_usage_against_the_plan(auth_client):
    await auth_client.post("/api/v1/watchers", json=payload(subreddits=["forhire", "jobs"]))

    response = await auth_client.get("/api/v1/me")

    body = response.json()
    assert body["user"]["plan"] == "free"
    assert body["usage"] == {
        "watchers_used": 1,
        "watchers_limit": 1,
        "subreddits_used": 2,
        "subreddits_limit": 3,
    }


async def test_me_on_a_fresh_account_reports_zero_usage(auth_client):
    response = await auth_client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json()["usage"]["watchers_used"] == 0
