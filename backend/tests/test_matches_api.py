"""Match feed endpoint tests against a real Postgres.

Marked `db` and skipped automatically when Postgres is unreachable — see tests/conftest.py.

Note that every row here sets `created_at` explicitly. Postgres' `now()` is transaction start
time, so rows inserted by one test would otherwise share a timestamp to the microsecond, and the
ordering and paging assertions would be testing the id tiebreak alone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.matched_post import MatchedPost
from app.models.user import User
from app.models.watcher import Watcher
from app.services.matches import decode_cursor, encode_cursor

pytestmark = pytest.mark.db

BASE_TIME = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


# Create a watcher owned by `user`, with the minimum a match needs to join through.
async def make_watcher(session: AsyncSession, user: User, name: str = "dev hiring") -> Watcher:
    watcher = Watcher(
        user_id=user.id,
        name=name,
        intent_text="someone looking to hire a developer for a web project",
        subreddits=["forhire"],
    )
    session.add(watcher)
    await session.commit()
    await session.refresh(watcher)
    return watcher


# Create a matched-post row. `reddit_post_id` is unique, so it gets a fresh value every call.
async def make_post(session: AsyncSession, title: str = "Need a dev") -> MatchedPost:
    suffix = uuid.uuid4().hex[:10]
    post = MatchedPost(
        reddit_post_id=f"t3_{suffix}",
        subreddit="forhire",
        title=title,
        body="body text",
        author="someone",
        permalink=f"https://reddit.com/r/forhire/comments/{suffix}",
        posted_at=BASE_TIME,
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


# Create a match row (every stored match is a confirmed one).
async def make_match(
    session: AsyncSession,
    watcher: Watcher,
    post: MatchedPost,
    minutes_ago: int = 0,
    read: bool = False,
) -> Match:
    match = Match(
        watcher_id=watcher.id,
        matched_post_id=post.id,
        llm_reason="They are asking for exactly this work.",
        llm_model="fake-model",
        created_at=BASE_TIME - timedelta(minutes=minutes_ago),
        read_at=BASE_TIME if read else None,
    )
    session.add(match)
    await session.commit()
    await session.refresh(match)
    return match


# --- What appears in the feed ------------------------------------------------------------------


async def test_feed_returns_confirmed_matches(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    post = await make_post(db_session, title="Looking for a React dev")
    await make_match(db_session, watcher, post)

    response = await auth_client.get("/api/v1/matches")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["post"]["title"] == "Looking for a React dev"
    assert item["watcher"]["name"] == "dev hiring"
    assert item["reason"] == "They are asking for exactly this work."
    assert item["read_at"] is None


async def test_feed_is_newest_first(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    for index, minutes in enumerate([30, 10, 20]):
        post = await make_post(db_session, title=f"post-{index}")
        await make_match(db_session, watcher, post, minutes_ago=minutes)

    items = (await auth_client.get("/api/v1/matches")).json()["items"]

    assert [item["post"]["title"] for item in items] == ["post-1", "post-2", "post-0"]


# --- Ownership ----------------------------------------------------------------------------------


async def test_another_users_matches_are_invisible(auth_client, db_session, db_user):
    stranger = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:12]}", email="o@example.com")
    db_session.add(stranger)
    await db_session.commit()

    their_watcher = await make_watcher(db_session, stranger, name="not yours")
    await make_match(db_session, their_watcher, await make_post(db_session))

    assert (await auth_client.get("/api/v1/matches")).json()["items"] == []


async def test_watcher_filter_cannot_reach_another_users_watcher(
    auth_client, db_session, db_user
):
    stranger = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:12]}", email="o@example.com")
    db_session.add(stranger)
    await db_session.commit()

    their_watcher = await make_watcher(db_session, stranger, name="not yours")
    await make_match(db_session, their_watcher, await make_post(db_session))

    # Filtering by a watcher id the caller does not own must return nothing, not that watcher's
    # feed. The filter narrows a user-scoped query; it never replaces the user scope.
    response = await auth_client.get(f"/api/v1/matches?watcher_id={their_watcher.id}")

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_watcher_filter_narrows_to_one_watcher(auth_client, db_session, db_user):
    first = await make_watcher(db_session, db_user, name="first")
    second = await make_watcher(db_session, db_user, name="second")
    await make_match(db_session, first, await make_post(db_session, title="for-first"))
    await make_match(db_session, second, await make_post(db_session, title="for-second"))

    response = await auth_client.get(f"/api/v1/matches?watcher_id={second.id}")

    items = response.json()["items"]
    assert [item["post"]["title"] for item in items] == ["for-second"]


# --- Paging --------------------------------------------------------------------------------------


async def test_cursor_pages_without_gaps_or_repeats(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    for index in range(5):
        post = await make_post(db_session, title=f"post-{index}")
        await make_match(db_session, watcher, post, minutes_ago=index)

    first = (await auth_client.get("/api/v1/matches?limit=2")).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    second = (
        await auth_client.get(f"/api/v1/matches?limit=2&cursor={first['next_cursor']}")
    ).json()
    third = (
        await auth_client.get(f"/api/v1/matches?limit=2&cursor={second['next_cursor']}")
    ).json()

    seen = [item["post"]["title"] for page in (first, second, third) for item in page["items"]]
    assert seen == ["post-0", "post-1", "post-2", "post-3", "post-4"]
    assert third["next_cursor"] is None


async def test_a_new_match_does_not_shift_the_next_page(auth_client, db_session, db_user):
    """The reason this feed uses a cursor rather than OFFSET.

    A match arriving between two page reads shifts an OFFSET window by one, so the row that was
    at the bottom of page 1 reappears at the top of page 2. A keyset cursor is immune.
    """
    watcher = await make_watcher(db_session, db_user)
    for index in range(4):
        post = await make_post(db_session, title=f"post-{index}")
        await make_match(db_session, watcher, post, minutes_ago=index + 1)

    first = (await auth_client.get("/api/v1/matches?limit=2")).json()

    # A newer match lands at the head of the feed while the user is reading.
    await make_match(
        db_session, watcher, await make_post(db_session, title="brand-new"), minutes_ago=0
    )

    second = (
        await auth_client.get(f"/api/v1/matches?limit=2&cursor={first['next_cursor']}")
    ).json()

    page_one = [item["post"]["title"] for item in first["items"]]
    page_two = [item["post"]["title"] for item in second["items"]]
    assert page_one == ["post-0", "post-1"]
    assert page_two == ["post-2", "post-3"]
    assert not set(page_one) & set(page_two)


async def test_matches_sharing_a_timestamp_all_appear(auth_client, db_session, db_user):
    """Timestamps collide — the matcher writes a batch in one transaction.

    Paging on `created_at` alone would drop whichever siblings fell after the page boundary; the
    id in the sort key is what prevents that.
    """
    watcher = await make_watcher(db_session, db_user)
    for index in range(4):
        post = await make_post(db_session, title=f"post-{index}")
        await make_match(db_session, watcher, post, minutes_ago=5)

    first = (await auth_client.get("/api/v1/matches?limit=2")).json()
    second = (
        await auth_client.get(f"/api/v1/matches?limit=2&cursor={first['next_cursor']}")
    ).json()

    titles = [item["post"]["title"] for page in (first, second) for item in page["items"]]
    assert sorted(titles) == ["post-0", "post-1", "post-2", "post-3"]


async def test_a_malformed_cursor_is_a_400(auth_client):
    response = await auth_client.get("/api/v1/matches?cursor=not-a-real-cursor")
    assert response.status_code == 400


async def test_cursor_round_trips():
    when = datetime(2026, 7, 31, 9, 30, tzinfo=UTC)
    identifier = uuid.uuid4()

    decoded = decode_cursor(encode_cursor(when, identifier))

    assert decoded.created_at == when
    assert decoded.match_id == identifier


async def test_limit_is_capped(auth_client):
    assert (await auth_client.get("/api/v1/matches?limit=5000")).status_code == 422


# --- Read tracking --------------------------------------------------------------------------------


async def test_unread_count_counts_only_unread(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    await make_match(db_session, watcher, await make_post(db_session))
    await make_match(db_session, watcher, await make_post(db_session), read=True)

    assert (await auth_client.get("/api/v1/matches")).json()["unread"] == 1
    assert (await auth_client.get("/api/v1/me")).json()["unread_matches"] == 1


async def test_mark_read_stamps_the_match(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    match = await make_match(db_session, watcher, await make_post(db_session))

    response = await auth_client.post(f"/api/v1/matches/{match.id}/read")

    assert response.status_code == 200
    assert response.json()["read_at"] is not None
    assert (await auth_client.get("/api/v1/matches")).json()["unread"] == 0


async def test_mark_read_is_idempotent(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    match = await make_match(db_session, watcher, await make_post(db_session))

    first = (await auth_client.post(f"/api/v1/matches/{match.id}/read")).json()
    second = (await auth_client.post(f"/api/v1/matches/{match.id}/read")).json()

    # The timestamp answers "when did I first see this", so a second open must not move it.
    assert first["read_at"] == second["read_at"]


async def test_mark_read_on_another_users_match_is_404(auth_client, db_session, db_user):
    stranger = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:12]}", email="o@example.com")
    db_session.add(stranger)
    await db_session.commit()
    their_watcher = await make_watcher(db_session, stranger)
    match = await make_match(db_session, their_watcher, await make_post(db_session))

    response = await auth_client.post(f"/api/v1/matches/{match.id}/read")

    # 404 rather than 403: a 403 confirms the id exists.
    assert response.status_code == 404


async def test_mark_all_read_clears_the_badge(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    for _ in range(3):
        await make_match(db_session, watcher, await make_post(db_session))

    response = await auth_client.post("/api/v1/matches/read-all")

    assert response.json() == {"updated": 3, "unread": 0}
    assert (await auth_client.get("/api/v1/matches")).json()["unread"] == 0


async def test_mark_all_read_leaves_other_users_alone(auth_client, db_session, db_user):
    stranger = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:12]}", email="o@example.com")
    db_session.add(stranger)
    await db_session.commit()
    their_watcher = await make_watcher(db_session, stranger)
    their_match = await make_match(db_session, their_watcher, await make_post(db_session))

    await auth_client.post("/api/v1/matches/read-all")

    await db_session.refresh(their_match)
    assert their_match.read_at is None
