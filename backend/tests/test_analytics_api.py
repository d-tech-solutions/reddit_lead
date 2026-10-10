"""Analytics endpoint tests against a real Postgres (marked `db`, skipped without one).

Dates are relative to now, not fixed: the endpoint windows on the current UTC day. Verdict totals
come from the daily `match_stats` counters; the "recently rejected" list comes from `rejection_log`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.match_stats import MatchStats
from app.models.matched_post import MatchedPost
from app.models.rejection_log import RejectionLog
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


async def add_verdict(
    session: AsyncSession,
    watcher: Watcher,
    subreddit: str = "forhire",
    confirmed: bool = True,
    days_ago: float = 0,
) -> None:
    """Record one verdict the way the matcher does: a counter bump, plus a match if confirmed."""
    when = datetime.now(UTC) - timedelta(days=days_ago)
    stats = await session.get(MatchStats, (watcher.id, subreddit, when.date()))
    if stats is None:
        stats = MatchStats(
            watcher_id=watcher.id, subreddit=subreddit, day=when.date(), reviewed=0, confirmed=0
        )
        session.add(stats)
    stats.reviewed += 1

    if confirmed:
        stats.confirmed += 1
        suffix = uuid.uuid4().hex[:10]
        post = MatchedPost(
            reddit_post_id=f"t3_{suffix}",
            subreddit=subreddit,
            title="A post",
            body="body",
            author="someone",
            permalink=f"https://reddit.com/r/{subreddit}/comments/{suffix}",
        )
        session.add(post)
        await session.flush()
        session.add(
            Match(watcher_id=watcher.id, matched_post_id=post.id, llm_reason="reason", created_at=when)
        )
    await session.commit()


async def test_empty_account_returns_zeroed_dashboard(auth_client):
    response = await auth_client.get("/api/v1/analytics?days=7")

    assert response.status_code == 200
    body = response.json()
    assert body["totals"] == {"confirmed": 0, "rejected": 0, "pass_rate": None}
    assert len(body["daily"]) == 7
    assert all(entry["confirmed"] == 0 for entry in body["daily"])
    assert body["top_subreddits"] == []
    assert body["watchers"] == []
    assert body["recent_rejections"] == []


async def test_totals_split_confirmed_and_rejected(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    for _ in range(3):
        await add_verdict(db_session, watcher, confirmed=True)
    await add_verdict(db_session, watcher, confirmed=False)

    body = (await auth_client.get("/api/v1/analytics")).json()

    assert body["totals"]["confirmed"] == 3
    assert body["totals"]["rejected"] == 1
    assert body["totals"]["pass_rate"] == 0.75


async def test_window_excludes_old_days(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    await add_verdict(db_session, watcher, days_ago=1)
    await add_verdict(db_session, watcher, days_ago=20)

    week = (await auth_client.get("/api/v1/analytics?days=7")).json()
    month = (await auth_client.get("/api/v1/analytics?days=30")).json()

    assert week["totals"]["confirmed"] == 1
    assert month["totals"]["confirmed"] == 2
    assert sum(entry["confirmed"] for entry in week["daily"]) == 1


async def test_top_subreddits_ranked_by_confirmed(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user)
    await add_verdict(db_session, watcher, subreddit="forhire")
    await add_verdict(db_session, watcher, subreddit="webdev")
    await add_verdict(db_session, watcher, subreddit="webdev")
    # Only rejected in this subreddit, so it must not appear at all.
    await add_verdict(db_session, watcher, subreddit="python", confirmed=False)

    body = (await auth_client.get("/api/v1/analytics")).json()

    assert [s["subreddit"] for s in body["top_subreddits"]] == ["webdev", "forhire"]
    assert body["top_subreddits"][0]["confirmed"] == 2


async def test_watchers_include_ones_with_no_activity(auth_client, db_session, db_user):
    busy = await make_watcher(db_session, db_user, name="busy")
    await make_watcher(db_session, db_user, name="quiet")
    await add_verdict(db_session, busy)
    await add_verdict(db_session, busy, confirmed=False)

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


async def test_recent_rejections_list_newest_first_with_reasons(auth_client, db_session, db_user):
    watcher = await make_watcher(db_session, db_user, name="busy")
    now = datetime.now(UTC)
    for index, minutes in enumerate([30, 10, 20]):
        db_session.add(
            RejectionLog(
                watcher_id=watcher.id,
                subreddit="forhire",
                reddit_post_id=f"t3_{index}",
                title=f"post-{index}",
                permalink=f"https://reddit.com/r/forhire/comments/{index}",
                reason=f"reason-{index}",
                created_at=now - timedelta(minutes=minutes),
            )
        )
    await db_session.commit()

    body = (await auth_client.get("/api/v1/analytics")).json()

    assert [r["title"] for r in body["recent_rejections"]] == ["post-1", "post-2", "post-0"]
    first = body["recent_rejections"][0]
    assert (first["watcher_name"], first["reason"]) == ("busy", "reason-1")


async def test_other_users_data_is_not_counted_or_listed(auth_client, db_session, db_user):
    other = User(clerk_user_id=f"user_other_{uuid.uuid4().hex[:8]}", email="other@example.com")
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    theirs = await make_watcher(db_session, other, name="theirs")
    await add_verdict(db_session, theirs)
    db_session.add(
        RejectionLog(
            watcher_id=theirs.id,
            subreddit="forhire",
            reddit_post_id="t3_x",
            title="theirs",
            permalink="https://reddit.com/x",
            reason="no",
        )
    )
    await db_session.commit()

    body = (await auth_client.get("/api/v1/analytics")).json()

    assert body["totals"]["confirmed"] == 0
    assert body["watchers"] == []
    assert body["recent_rejections"] == []
