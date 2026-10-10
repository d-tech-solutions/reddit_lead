"""Retention jobs against a real Postgres (marked `db`, skipped without one)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.matched_post import MatchedPost
from app.models.rejection_log import RejectionLog
from app.models.seen_post import SeenPost
from app.models.user import User
from app.models.watcher import Watcher
from app.services import retention

pytestmark = pytest.mark.db

OLD = datetime.now(UTC) - timedelta(days=120)


async def make_user(session: AsyncSession, last_active_at: datetime | None = None) -> User:
    user = User(clerk_user_id=f"user_test_{uuid.uuid4().hex[:12]}")
    if last_active_at is not None:
        user.last_active_at = last_active_at
    session.add(user)
    await session.commit()
    return user


async def make_match(
    session: AsyncSession, user: User, post_matched_at: datetime | None = None
) -> tuple[Match, MatchedPost]:
    watcher = Watcher(user_id=user.id, name="w", intent_text="x", subreddits=["forhire"])
    suffix = uuid.uuid4().hex[:10]
    post = MatchedPost(
        reddit_post_id=f"t3_{suffix}", subreddit="forhire", title="t", body="", permalink="p"
    )
    if post_matched_at is not None:
        post.matched_at = post_matched_at
    session.add_all([watcher, post])
    await session.flush()
    match = Match(watcher_id=watcher.id, matched_post_id=post.id)
    session.add(match)
    await session.commit()
    return match, post


async def exists(session: AsyncSession, model, **where) -> bool:
    query = select(func.count()).select_from(model)
    for column, value in where.items():
        query = query.where(getattr(model, column) == value)
    return (await session.execute(query)).scalar_one() > 0


async def test_prune_seen_posts_removes_only_rows_past_the_window(db_session):
    db_session.add_all(
        [
            SeenPost(reddit_post_id="old_seen", seen_at=datetime.now(UTC) - timedelta(days=30)),
            SeenPost(reddit_post_id="new_seen", seen_at=datetime.now(UTC)),
        ]
    )
    await db_session.commit()

    await retention.prune_seen_posts(db_session, days=7, batch=100)

    assert not await exists(db_session, SeenPost, reddit_post_id="old_seen")
    assert await exists(db_session, SeenPost, reddit_post_id="new_seen")


async def test_prune_runs_in_batches_until_done(db_session):
    db_session.add_all(
        [
            SeenPost(reddit_post_id=f"batch_{i}", seen_at=datetime.now(UTC) - timedelta(days=30))
            for i in range(5)
        ]
    )
    await db_session.commit()

    removed = await retention.prune_seen_posts(db_session, days=7, batch=2)

    assert removed >= 5
    assert not await exists(db_session, SeenPost, reddit_post_id="batch_4")


async def test_prune_rejection_log_removes_old_samples(db_session):
    user = await make_user(db_session)
    watcher = Watcher(user_id=user.id, name="w", intent_text="x", subreddits=["forhire"])
    db_session.add(watcher)
    await db_session.flush()
    for title, age in (("old", timedelta(days=30)), ("new", timedelta(hours=1))):
        db_session.add(
            RejectionLog(
                watcher_id=watcher.id,
                subreddit="forhire",
                reddit_post_id=f"t3_{title}",
                title=title,
                permalink="p",
                reason="no",
                created_at=datetime.now(UTC) - age,
            )
        )
    await db_session.commit()

    await retention.prune_rejection_log(db_session, days=7, batch=100)

    assert not await exists(db_session, RejectionLog, title="old")
    assert await exists(db_session, RejectionLog, title="new")


async def test_inactive_users_lose_their_matches_active_users_keep_theirs(db_session):
    inactive = await make_user(db_session, last_active_at=OLD)
    active = await make_user(db_session)
    gone, _ = await make_match(db_session, inactive)
    kept, _ = await make_match(db_session, active)

    await retention.purge_inactive_user_matches(db_session, days=90, batch=100)

    assert not await exists(db_session, Match, id=gone.id)
    assert await exists(db_session, Match, id=kept.id)


async def test_orphaned_matched_posts_are_collected_but_referenced_ones_are_not(db_session):
    user = await make_user(db_session)
    _, referenced = await make_match(db_session, user, post_matched_at=OLD)
    orphan = MatchedPost(
        reddit_post_id=f"t3_{uuid.uuid4().hex[:10]}",
        subreddit="forhire",
        title="orphan",
        body="",
        permalink="p",
        matched_at=OLD,
    )
    fresh_orphan = MatchedPost(
        reddit_post_id=f"t3_{uuid.uuid4().hex[:10]}",
        subreddit="forhire",
        title="fresh orphan",
        body="",
        permalink="p",
    )
    db_session.add_all([orphan, fresh_orphan])
    await db_session.commit()

    await retention.purge_orphan_matched_posts(db_session, batch=100)

    assert not await exists(db_session, MatchedPost, id=orphan.id)
    assert await exists(db_session, MatchedPost, id=referenced.id)
    # Inside the grace period, so a row can't be collected before its matches are written.
    assert await exists(db_session, MatchedPost, id=fresh_orphan.id)


async def test_inactivity_purge_then_orphan_sweep_removes_the_post_too(db_session):
    inactive = await make_user(db_session, last_active_at=OLD)
    match, post = await make_match(db_session, inactive, post_matched_at=OLD)

    await retention.purge_inactive_user_matches(db_session, days=90, batch=100)
    await retention.purge_orphan_matched_posts(db_session, batch=100)

    assert not await exists(db_session, Match, id=match.id)
    assert not await exists(db_session, MatchedPost, id=post.id)
