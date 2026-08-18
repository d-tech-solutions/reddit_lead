"""Matcher worker tests.

`chunk_watchers` is pure logic and needs no database. Everything else touches real SQL (the
`ON CONFLICT DO NOTHING` insert, the `IN (...)` update, the `NOT EXISTS` sweep query), so those
tests run against a real, rolled-back Postgres — same convention as test_watchers_api.py and
test_matches_api.py, rather than a hand-rolled session fake that wouldn't exercise the actual
queries.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.reddit_post import RedditPost
from app.models.user import User
from app.models.watcher import Watcher
from app.workers import match
from app.workers.verifier import Verdict
from tests.conftest import FakeVerifier


def make_watcher_obj(name: str = "w", intent_text: str = "someone hiring a developer") -> Watcher:
    watcher = Watcher(name=name, intent_text=intent_text, subreddits=["forhire"], status="active")
    watcher.id = uuid.uuid4()
    return watcher


# --- chunk_watchers (no DB) ---------------------------------------------------------------------


def test_chunk_watchers_splits_into_fixed_size_groups():
    watchers = [make_watcher_obj(name=f"w{i}") for i in range(7)]

    chunks = match.chunk_watchers(watchers, 3)

    assert [len(chunk) for chunk in chunks] == [3, 3, 1]


def test_chunk_watchers_with_fewer_watchers_than_the_batch_size_is_one_chunk():
    assert len(match.chunk_watchers([make_watcher_obj()], 10)) == 1


def test_chunk_watchers_with_no_watchers_returns_nothing():
    assert match.chunk_watchers([], 10) == []


@pytest.mark.parametrize(
    ("interval", "expected_count"),
    [(5, 12), (1, 60), (15, 4), (60, 1), (7, 10), (0, 60)],
)
def test_backfill_minutes_builds_an_even_schedule(interval, expected_count):
    minutes = match.backfill_minutes(interval)
    assert len(minutes) == expected_count
    assert 0 in minutes


# --- DB-backed tests -----------------------------------------------------------------------------

pytestmark = pytest.mark.db


async def make_user(session: AsyncSession) -> User:
    user = User(clerk_user_id=f"user_test_{uuid.uuid4().hex[:12]}")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def make_db_watcher(
    session: AsyncSession,
    user: User,
    name: str = "dev hiring",
    intent_text: str = "someone looking to hire a developer",
    subreddits: list[str] | None = None,
    status: str = "active",
) -> Watcher:
    watcher = Watcher(
        user_id=user.id,
        name=name,
        intent_text=intent_text,
        subreddits=subreddits if subreddits is not None else ["forhire"],
        status=status,
    )
    session.add(watcher)
    await session.commit()
    await session.refresh(watcher)
    return watcher


async def make_db_post(
    session: AsyncSession, subreddit: str = "forhire", title: str = "Need a developer"
) -> RedditPost:
    suffix = uuid.uuid4().hex[:10]
    post = RedditPost(
        reddit_post_id=f"t3_{suffix}",
        subreddit=subreddit,
        title=title,
        body="",
        permalink=f"https://reddit.com/r/{subreddit}/comments/{suffix}",
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


def fake_settings(batch_size: int = 15, backfill_limit: int = 200) -> SimpleNamespace:
    return SimpleNamespace(MATCH_BATCH_SIZE=batch_size, MATCH_BACKFILL_LIMIT=backfill_limit)


@asynccontextmanager
async def _reuse_session(session: AsyncSession):
    # match_post/backfill each open their own session via `async_session_factory()`; this swaps
    # that for the test's rolled-back transaction so their commits stay inside it.
    yield session


async def test_fetch_candidate_watchers_filters_by_subreddit_and_status(db_session):
    user = await make_user(db_session)
    matching = await make_db_watcher(db_session, user, name="matching", subreddits=["forhire"])
    await make_db_watcher(db_session, user, name="other-sub", subreddits=["slavelabour"])
    await make_db_watcher(db_session, user, name="paused", subreddits=["forhire"], status="paused")

    candidates = await match.fetch_candidate_watchers(db_session, "forhire")

    assert [w.name for w in candidates] == [matching.name]


async def test_store_placeholder_matches_is_idempotent(db_session):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    post = await make_db_post(db_session)

    first = await match.store_placeholder_matches(db_session, post.id, [watcher.id])
    second = await match.store_placeholder_matches(db_session, post.id, [watcher.id])

    assert len(first) == 1
    # ON CONFLICT DO NOTHING against uq_matches_pair — no duplicate row, nothing new returned.
    assert second == []


async def test_store_placeholder_matches_leaves_llm_verified_null(db_session):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    post = await make_db_post(db_session)

    [match_id] = await match.store_placeholder_matches(db_session, post.id, [watcher.id])

    row = await db_session.get(Match, match_id)
    assert row.llm_verified is None


async def test_apply_verdicts_records_a_positive_and_a_negative_verdict(db_session):
    user = await make_user(db_session)
    watcher_a = await make_db_watcher(db_session, user, name="a")
    watcher_b = await make_db_watcher(db_session, user, name="b")
    post = await make_db_post(db_session)
    await match.store_placeholder_matches(db_session, post.id, [watcher_a.id, watcher_b.id])

    confirmed = await match.apply_verdicts(
        db_session,
        post.id,
        [
            Verdict(watcher_id=watcher_a.id, matches=True, reason="yes", model="m"),
            Verdict(watcher_id=watcher_b.id, matches=False, reason="no", model="m"),
        ],
    )

    assert confirmed == 1
    result = await db_session.execute(select(Match).where(Match.reddit_post_id == post.id))
    by_watcher = {row.watcher_id: row for row in result.scalars()}
    assert by_watcher[watcher_a.id].llm_verified is True
    assert by_watcher[watcher_a.id].verified_at is not None
    assert by_watcher[watcher_b.id].llm_verified is False


async def test_apply_verdicts_skips_an_already_judged_row(db_session):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    post = await make_db_post(db_session)
    [match_id] = await match.store_placeholder_matches(db_session, post.id, [watcher.id])
    row = await db_session.get(Match, match_id)
    row.llm_verified = False
    row.llm_reason = "already judged"
    await db_session.commit()

    confirmed = await match.apply_verdicts(
        db_session,
        post.id,
        [Verdict(watcher_id=watcher.id, matches=True, reason="new", model="m")],
    )

    assert confirmed == 0
    await db_session.refresh(row)
    assert row.llm_reason == "already judged"


async def test_apply_verdicts_ignores_a_verdict_with_no_matching_row(db_session):
    confirmed = await match.apply_verdicts(
        db_session,
        uuid.uuid4(),
        [Verdict(watcher_id=uuid.uuid4(), matches=True, reason="x", model="m")],
    )
    assert confirmed == 0


async def test_match_post_writes_and_verifies_every_candidate(db_session, monkeypatch):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    post = await make_db_post(db_session)
    verifier = FakeVerifier(matches=True)

    monkeypatch.setattr(match, "async_session_factory", lambda: _reuse_session(db_session))

    confirmed = await match.match_post(
        {"verifier": verifier, "settings": fake_settings()}, str(post.id)
    )

    assert confirmed == 1
    assert len(verifier.calls) == 1
    _, _, candidates = verifier.calls[0]
    assert candidates == [(watcher.id, watcher.intent_text)]


async def test_match_post_with_no_candidate_watchers_writes_nothing(db_session, monkeypatch):
    post = await make_db_post(db_session, subreddit="nobody_watches_this")
    verifier = FakeVerifier()
    monkeypatch.setattr(match, "async_session_factory", lambda: _reuse_session(db_session))

    confirmed = await match.match_post(
        {"verifier": verifier, "settings": fake_settings()}, str(post.id)
    )

    assert confirmed == 0
    assert verifier.calls == []


async def test_match_post_splits_a_large_candidate_set_into_batches(db_session, monkeypatch):
    user = await make_user(db_session)
    for index in range(5):
        await make_db_watcher(db_session, user, name=f"w{index}")
    post = await make_db_post(db_session)
    verifier = FakeVerifier(matches=False)
    monkeypatch.setattr(match, "async_session_factory", lambda: _reuse_session(db_session))

    await match.match_post({"verifier": verifier, "settings": fake_settings(batch_size=2)}, str(post.id))

    assert len(verifier.calls) == 3  # 5 watchers, batch size 2 → 2 + 2 + 1


async def test_match_post_survives_a_failing_batch(db_session, monkeypatch):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user, intent_text="boom")
    post = await make_db_post(db_session)
    verifier = FakeVerifier(fail_on={"boom"})
    monkeypatch.setattr(match, "async_session_factory", lambda: _reuse_session(db_session))

    confirmed = await match.match_post(
        {"verifier": verifier, "settings": fake_settings()}, str(post.id)
    )

    # The batch failed, so nothing was confirmed — but the placeholder row must survive for the
    # backfill sweep to retry, not be lost or half-written.
    assert confirmed == 0
    result = await db_session.execute(
        select(Match).where(Match.reddit_post_id == post.id, Match.watcher_id == watcher.id)
    )
    assert result.scalar_one().llm_verified is None


async def test_backfill_verifies_unjudged_candidates(db_session, monkeypatch):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    post = await make_db_post(db_session)
    await match.store_placeholder_matches(db_session, post.id, [watcher.id])
    verifier = FakeVerifier(matches=True)
    monkeypatch.setattr(match, "async_session_factory", lambda: _reuse_session(db_session))

    handled = await match.backfill({"verifier": verifier, "settings": fake_settings()})

    assert handled == 1
    result = await db_session.execute(
        select(Match).where(Match.reddit_post_id == post.id, Match.watcher_id == watcher.id)
    )
    assert result.scalar_one().llm_verified is True


async def test_backfill_gates_a_post_no_job_ever_ran_for(db_session, monkeypatch):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    post = await make_db_post(db_session)  # never went through match_post or store_placeholder
    verifier = FakeVerifier(matches=True)
    monkeypatch.setattr(match, "async_session_factory", lambda: _reuse_session(db_session))

    handled = await match.backfill({"verifier": verifier, "settings": fake_settings()})

    assert handled == 1
    result = await db_session.execute(
        select(Match).where(Match.reddit_post_id == post.id, Match.watcher_id == watcher.id)
    )
    assert result.scalar_one().llm_verified is True
