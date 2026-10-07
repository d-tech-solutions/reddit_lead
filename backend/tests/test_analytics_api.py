"""Analytics endpoint tests against a real Postgres (marked `db`, skipped without one).

Match timestamps are relative to now, not a fixed date: the endpoint windows on the current time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.reddit_post import RedditPost
from app.models.user import User
from app.models.watcher import Watcher

pytestmark = pytest.mark.db


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


async def add_match(
    session: AsyncSession,
    watcher: Watcher,
    subreddit: str = "forhire",
    verified: bool | None = True,
    days_ago: float = 0,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    post = RedditPost(
        reddit_post_id=f"t3_{suffix}",
        subreddit=subreddit,
        title="A post",
        body="body",
        author="someone",
        permalink=f"https://reddit.com/r/{subreddit}/comments/{suffix}",
        posted_at=datetime.now(UTC),
    )
    session.add(post)
    await session.flush()
    session.add(
        Match(
            watcher_id=watcher.id,
            reddit_post_id=post.id,
            llm_verified=verified,
            llm_reason="reason",
            created_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    await session.commit()


async def test_empty_account_returns_zeroed_dashboard(auth_client):
    response = await auth_client.get("/api/v1/analytics?days=7")

    assert response.status_code == 200
    body = response.json()
    assert body["totals"] == {"confirmed": 0, "rejected": 0, "pending": 0, "pass_rate": None}
    assert len(body["daily"]) == 7
    assert all(entry["confirmed"] == 0 for entry in body["daily"])
    assert body["top_subreddits"] == []
    assert body["watchers"] == []


async def test_totals_split_verdicts_and_ignore_pending_in_rate(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    await add_match(db_session, watcher, verified=True)
    await add_match(db_session, watcher, verified=True)
    await add_match(db_session, watcher, verified=True)
    await add_match(db_session, watcher, verified=False)
    await add_match(db_session, watcher, verified=None)

    body = (await auth_client.get("/api/v1/analytics")).json()

    assert body["totals"]["confirmed"] == 3
    assert body["totals"]["rejected"] == 1
    assert body["totals"]["pending"] == 1
    assert body["totals"]["pass_rate"] == 0.75


async def test_window_excludes_old_matches(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    await add_match(db_session, watcher, days_ago=1)
    await add_match(db_session, watcher, days_ago=20)

    week = (await auth_client.get("/api/v1/analytics?days=7")).json()
    month = (await auth_client.get("/api/v1/analytics?days=30")).json()

    assert week["totals"]["confirmed"] == 1
    assert month["totals"]["confirmed"] == 2
    assert sum(entry["confirmed"] for entry in week["daily"]) == 1


async def test_top_subreddits_ranked_by_confirmed(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    await add_match(db_session, watcher, subreddit="forhire")
    await add_match(db_session, watcher, subreddit="webdev")
    await add_match(db_session, watcher, subreddit="webdev")
    # Only rejected in this subreddit, so it must not appear at all.
    await add_match(db_session, watcher, subreddit="python", verified=False)

    body = (await auth_client.get("/api/v1/analytics")).json()

    assert [s["subreddit"] for s in body["top_subreddits"]] == ["webdev", "forhire"]
    assert body["top_subreddits"][0]["confirmed"] == 2


async def test_watchers_include_ones_with_no_matches(auth_client, db_session, db_user):
    busy = await make_watcher(db_session, db_user, name="busy")
    await make_watcher(db_session, db_user, name="quiet")
    await add_match(db_session, busy)
    await add_match(db_session, busy, verified=False)

    body = (await auth_client.get("/api/v1/analytics")).json()

    by_name = {w["name"]: w for w in body["watchers"]}
    assert by_name["busy"]["confirmed"] == 1
    assert by_name["busy"]["reviewed"] == 2
    assert by_name["busy"]["pass_rate"] == 0.5
    assert by_name["busy"]["last_match_at"] is not None
    assert by_name["quiet"]["confirmed"] == 0
    assert by_name["quiet"]["pass_rate"] is None
    assert by_name["quiet"]["last_match_at"] is None
    assert body["watchers"][0]["name"] == "busy"


async def test_other_users_matches_are_not_counted(auth_client, db_session, db_user):
    other = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:8]}", email="other@example.com")
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    theirs = await make_watcher(db_session, other, name="theirs")
    await add_match(db_session, theirs)

    body = (await auth_client.get("/api/v1/analytics")).json()

    assert body["totals"]["confirmed"] == 0
    assert body["watchers"] == []
