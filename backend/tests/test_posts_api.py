"""Post feed endpoint tests against a real Postgres.

Marked `db` and skipped automatically when Postgres is unreachable — see tests/conftest.py.

Admin-only (see `app.api.v1.endpoints.posts`): scoped to every subreddit anything has ever been
ingested from, not to the caller's own watchers, so `admin_client`/`db_admin_user` stand in for the
caller throughout rather than `auth_client`/`db_user`.

That global scope means these tests can't rely on an empty table the way the old per-user-scoped
tests could — this Postgres instance also carries whatever a developer has ingested for real, and
the shared `db_session` fixture only rolls back what *this* test itself commits. Every test below
therefore invents its own unique subreddit name(s) (`unique_subreddit()`) so its rows can never
collide with, or get lost among, unrelated data already sitting in the table.

Every row sets `fetched_at` explicitly for the same reason `test_matches_api.py` sets
`created_at`: Postgres' `now()` is transaction start time, so rows inserted by one test would
otherwise share a timestamp to the microsecond and the ordering/paging assertions would only be
testing the id tiebreak.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reddit_post import RedditPost
from app.models.user import User
from app.models.watcher import Watcher
from app.services.posts import decode_cursor, encode_cursor

pytestmark = pytest.mark.db

BASE_TIME = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


def unique_subreddit() -> str:
    return f"t{uuid.uuid4().hex[:12]}"


# Create a watcher owned by `user`, watching `subreddits`.
async def make_watcher(
    session: AsyncSession, user: User, subreddits: list[str], name: str = "dev hiring"
) -> Watcher:
    watcher = Watcher(
        user_id=user.id,
        name=name,
        intent_text="someone looking to hire a developer for a web project",
        subreddits=subreddits,
    )
    session.add(watcher)
    await session.commit()
    await session.refresh(watcher)
    return watcher


# Create a Reddit post row. `reddit_post_id` is unique, so it gets a fresh value every call.
async def make_post(
    session: AsyncSession,
    subreddit: str,
    title: str = "Need a dev",
    minutes_ago: int = 0,
) -> RedditPost:
    suffix = uuid.uuid4().hex[:10]
    post = RedditPost(
        reddit_post_id=f"t3_{suffix}",
        subreddit=subreddit,
        title=title,
        body="body text",
        author="someone",
        permalink=f"https://reddit.com/r/{subreddit}/comments/{suffix}",
        posted_at=BASE_TIME,
        fetched_at=BASE_TIME - timedelta(minutes=minutes_ago),
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


async def test_non_admin_is_refused(auth_client, db_session):
    await make_post(db_session, subreddit=unique_subreddit())
    response = await auth_client.get("/api/v1/posts")
    assert response.status_code == 403


# --- Scope: every ingested subreddit, not just the admin's own watchers ------------------------


async def test_admin_sees_posts_from_subreddits_they_do_not_personally_watch(
    admin_client, db_session, db_admin_user
):
    # The admin has no watcher at all here — the pipeline-wide view doesn't depend on one.
    sub_a, sub_b = unique_subreddit(), unique_subreddit()
    await make_post(db_session, subreddit=sub_a, title="in scope")
    await make_post(db_session, subreddit=sub_b, title="also in scope")

    unfiltered = await admin_client.get("/api/v1/posts")
    assert unfiltered.status_code == 200
    # The chip list isn't paginated, so it reflects every subreddit regardless of how deep in the
    # (potentially much larger, real-data-carrying) unfiltered feed a given post actually sits.
    assert {sub_a, sub_b} <= set(unfiltered.json()["subreddits"])

    # The unfiltered `items` page only holds the newest N posts overall, which unrelated data in
    # this Postgres instance could easily push these two off of — filtering per subreddit is what
    # actually proves each one is reachable.
    for subreddit, title in [(sub_a, "in scope"), (sub_b, "also in scope")]:
        response = await admin_client.get(f"/api/v1/posts?subreddit={subreddit}")
        assert [item["title"] for item in response.json()["items"]] == [title]


async def test_another_users_watchers_do_not_limit_what_the_admin_sees(
    admin_client, db_session, db_user
):
    watched, unwatched = unique_subreddit(), unique_subreddit()
    await make_watcher(db_session, db_user, subreddits=[watched])
    await make_post(db_session, subreddit=watched, title="watched by someone")
    await make_post(db_session, subreddit=unwatched, title="watched by no one")

    for subreddit, title in [(watched, "watched by someone"), (unwatched, "watched by no one")]:
        response = await admin_client.get(f"/api/v1/posts?subreddit={subreddit}")
        assert [item["title"] for item in response.json()["items"]] == [title]


# --- Post fields ----------------------------------------------------------------------------------


async def test_post_fields_include_body_author_and_both_timestamps(admin_client, db_session):
    subreddit = unique_subreddit()
    await make_post(db_session, subreddit=subreddit, title="Looking for a React dev")

    response = await admin_client.get(f"/api/v1/posts?subreddit={subreddit}")
    item = response.json()["items"][0]

    assert item["title"] == "Looking for a React dev"
    assert item["body"] == "body text"
    assert item["author"] == "someone"
    assert item["posted_at"] is not None
    assert item["fetched_at"] is not None


# --- Subreddit filter -----------------------------------------------------------------------------


async def test_subreddit_filter_narrows_to_one_subreddit(admin_client, db_session):
    sub_a, sub_b = unique_subreddit(), unique_subreddit()
    await make_post(db_session, subreddit=sub_a, title="for-a")
    await make_post(db_session, subreddit=sub_b, title="for-b")

    response = await admin_client.get(f"/api/v1/posts?subreddit={sub_b}")

    items = response.json()["items"]
    assert [item["title"] for item in items] == ["for-b"]


async def test_subreddit_filter_cannot_reach_a_subreddit_nothing_was_ingested_from(
    admin_client, db_session
):
    await make_post(db_session, subreddit=unique_subreddit())

    response = await admin_client.get(f"/api/v1/posts?subreddit={unique_subreddit()}")

    assert response.status_code == 200
    assert response.json()["items"] == []


# --- Paging --------------------------------------------------------------------------------------
# Filtered to one made-up subreddit throughout, so ordering/paging assertions aren't at the mercy
# of however much unrelated data this Postgres instance already carries.


async def test_posts_are_newest_fetched_first(admin_client, db_session):
    subreddit = unique_subreddit()
    for index, minutes in enumerate([30, 10, 20]):
        await make_post(db_session, subreddit=subreddit, title=f"post-{index}", minutes_ago=minutes)

    items = (await admin_client.get(f"/api/v1/posts?subreddit={subreddit}")).json()["items"]

    assert [item["title"] for item in items] == ["post-1", "post-2", "post-0"]


async def test_cursor_pages_without_gaps_or_repeats(admin_client, db_session):
    subreddit = unique_subreddit()
    for index in range(5):
        await make_post(db_session, subreddit=subreddit, title=f"post-{index}", minutes_ago=index)

    first = (
        await admin_client.get(f"/api/v1/posts?subreddit={subreddit}&limit=2")
    ).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    second = (
        await admin_client.get(
            f"/api/v1/posts?subreddit={subreddit}&limit=2&cursor={first['next_cursor']}"
        )
    ).json()
    third = (
        await admin_client.get(
            f"/api/v1/posts?subreddit={subreddit}&limit=2&cursor={second['next_cursor']}"
        )
    ).json()

    seen = [item["title"] for page in (first, second, third) for item in page["items"]]
    assert seen == ["post-0", "post-1", "post-2", "post-3", "post-4"]
    assert third["next_cursor"] is None


async def test_a_malformed_cursor_is_a_400(admin_client):
    response = await admin_client.get("/api/v1/posts?cursor=not-a-real-cursor")
    assert response.status_code == 400


async def test_cursor_round_trips():
    when = datetime(2026, 7, 31, 9, 30, tzinfo=UTC)
    identifier = uuid.uuid4()

    decoded = decode_cursor(encode_cursor(when, identifier))

    assert decoded.fetched_at == when
    assert decoded.post_id == identifier


async def test_limit_is_capped(admin_client):
    assert (await admin_client.get("/api/v1/posts?limit=5000")).status_code == 422
