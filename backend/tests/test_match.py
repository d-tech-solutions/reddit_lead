"""Matcher worker tests.

`chunk_candidates` and `backfill_minutes` are pure logic. Everything else touches real SQL (the
`FOR UPDATE SKIP LOCKED` claim, the `@>` candidate lookup, the multi-row upserts), so those tests
run against a real, rolled-back Postgres — same convention as test_watchers_api.py, rather than a
hand-rolled session fake that wouldn't exercise the actual queries.

The development database also carries real watchers and queued posts, so every DB test uses its own
unique subreddit (`unique_sub()`) and asserts on its own rows by id, never on whole-table counts.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.match_stats import MatchStats
from app.models.matched_post import MatchedPost
from app.models.reddit_post import RedditPost
from app.models.rejection_log import RejectionLog
from app.models.user import User
from app.models.watcher import Watcher
from app.workers import match
from tests.conftest import FakeVerifier

# --- pure logic (no DB) -------------------------------------------------------------------------


def test_chunk_candidates_splits_into_fixed_size_groups():
    candidates = [(uuid.uuid4(), f"intent {i}") for i in range(7)]

    chunks = match.chunk_candidates(candidates, 3)

    assert [len(chunk) for chunk in chunks] == [3, 3, 1]


def test_chunk_candidates_with_fewer_candidates_than_the_batch_size_is_one_chunk():
    assert len(match.chunk_candidates([(uuid.uuid4(), "x")], 10)) == 1


def test_chunk_candidates_with_no_candidates_returns_nothing():
    assert match.chunk_candidates([], 10) == []


@pytest.mark.parametrize(
    ("interval", "expected_count"),
    [(5, 12), (1, 60), (15, 4), (60, 1), (7, 10), (0, 60)],
)
def test_backfill_minutes_builds_an_even_schedule(interval, expected_count):
    minutes = match.backfill_minutes(interval)
    assert len(minutes) == expected_count
    assert 0 in minutes


# --- DB-backed helpers ---------------------------------------------------------------------------


def unique_sub() -> str:
    """A subreddit no real data uses, so a test only ever sees its own watchers and posts."""
    return f"t{uuid.uuid4().hex[:12]}"


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
    created_at: datetime | None = None,
) -> Watcher:
    watcher = Watcher(
        user_id=user.id,
        name=name,
        intent_text=intent_text,
        subreddits=subreddits if subreddits is not None else ["forhire"],
        status=status,
    )
    if created_at is not None:
        watcher.created_at = created_at
    session.add(watcher)
    await session.commit()
    await session.refresh(watcher)
    return watcher


async def make_db_post(
    session: AsyncSession,
    subreddit: str = "forhire",
    title: str = "Need a developer",
    posted_at: datetime | None = None,
    attempts: int = 0,
) -> RedditPost:
    suffix = uuid.uuid4().hex[:10]
    post = RedditPost(
        reddit_post_id=f"t3_{suffix}",
        subreddit=subreddit,
        title=title,
        body="",
        permalink=f"https://reddit.com/r/{subreddit}/comments/{suffix}",
        posted_at=posted_at,
        attempts=attempts,
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


async def make_matched_post(
    session: AsyncSession, subreddit: str = "forhire", title: str = "Need a developer"
) -> MatchedPost:
    suffix = uuid.uuid4().hex[:10]
    post = MatchedPost(
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


def fake_settings(**overrides) -> SimpleNamespace:
    values = {
        "MATCH_BATCH_SIZE": 15,
        "MATCH_BACKFILL_LIMIT": 200,
        "MATCH_CLAIM_SECONDS": 300,
        "MATCH_BACKFILL_MIN_AGE_SECONDS": 0,
        "MATCH_MAX_ATTEMPTS": 5,
        "NEW_WATCHER_LOOKBACK_MINUTES": 60,
        "CATCHUP_MAX_POSTS": 50,
        "CATCHUP_BATCH_SIZE": 10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@asynccontextmanager
async def _reuse_session(session: AsyncSession):
    # match_post/backfill each open their own session via `async_session_factory()`; this swaps
    # that for the test's rolled-back transaction so their commits stay inside it.
    yield session


async def count(session: AsyncSession, model, **where) -> int:
    query = select(func.count()).select_from(model)
    for column, value in where.items():
        query = query.where(getattr(model, column) == value)
    return int((await session.execute(query)).scalar_one())


async def clear_queue(session: AsyncSession) -> None:
    """Empty the queue inside the test's (rolled-back) transaction so a sweep sees only this test."""
    await session.execute(delete(RedditPost))
    await session.commit()


async def stats_for(session: AsyncSession, watcher: Watcher) -> list[MatchStats]:
    result = await session.execute(select(MatchStats).where(MatchStats.watcher_id == watcher.id))
    return list(result.scalars())


@pytest.fixture
def use_session(db_session, monkeypatch):
    monkeypatch.setattr(match, "async_session_factory", lambda: _reuse_session(db_session))


# --- candidate lookup and claiming ---------------------------------------------------------------


@pytest.mark.db
async def test_fetch_candidate_watchers_filters_by_subreddit_status_and_age(db_session):
    sub = unique_sub()
    user = await make_user(db_session)
    now = datetime.now(UTC)
    matching = await make_db_watcher(db_session, user, name="matching", subreddits=[sub])
    await make_db_watcher(db_session, user, name="other-sub", subreddits=[unique_sub()])
    await make_db_watcher(db_session, user, name="paused", subreddits=[sub], status="paused")
    # Created after the post was made, so the catch-up job owns that post for this watcher.
    await make_db_watcher(
        db_session, user, name="too-new", subreddits=[sub], created_at=now + timedelta(hours=1)
    )

    candidates = await match.fetch_candidate_watchers(db_session, sub, now)

    assert candidates == [(matching.id, matching.intent_text)]


@pytest.mark.db
async def test_claim_post_leases_the_post_once(db_session):
    post = await make_db_post(db_session)

    first = await match.claim_post(db_session, post.id, 300)
    second = await match.claim_post(db_session, post.id, 300)

    assert first is not None
    assert first.attempts == 1
    assert first.locked_until > datetime.now(UTC)
    assert second is None  # the lease is still held


@pytest.mark.db
async def test_claim_post_takes_over_an_expired_lease(db_session):
    post = await make_db_post(db_session)
    post.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    claimed = await match.claim_post(db_session, post.id, 300)

    assert claimed is not None


# --- settling a post -----------------------------------------------------------------------------


@pytest.mark.db
async def test_confirmed_post_moves_to_matched_posts_and_leaves_the_queue(db_session, use_session):
    sub = unique_sub()
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user, subreddits=[sub])
    post = await make_db_post(db_session, subreddit=sub)
    verifier = FakeVerifier(matches=True)

    confirmed = await match.match_post(
        {"verifier": verifier, "settings": fake_settings()}, str(post.id)
    )

    assert confirmed == 1
    assert await count(db_session, RedditPost, id=post.id) == 0
    stored = (
        await db_session.execute(
            select(MatchedPost).where(MatchedPost.reddit_post_id == post.reddit_post_id)
        )
    ).scalar_one()
    row = (
        await db_session.execute(select(Match).where(Match.watcher_id == watcher.id))
    ).scalar_one()
    assert row.matched_post_id == stored.id
    assert row.llm_reason == "fake verdict"
    assert await count(db_session, RejectionLog, watcher_id=watcher.id) == 0
    [stats] = await stats_for(db_session, watcher)
    assert (stats.subreddit, stats.reviewed, stats.confirmed) == (sub, 1, 1)


@pytest.mark.db
async def test_rejected_post_is_deleted_and_only_counted_and_sampled(db_session, use_session):
    sub = unique_sub()
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user, subreddits=[sub])
    post = await make_db_post(db_session, subreddit=sub, title="Selling my old couch")
    verifier = FakeVerifier(matches=False)

    confirmed = await match.match_post(
        {"verifier": verifier, "settings": fake_settings()}, str(post.id)
    )

    assert confirmed == 0
    assert await count(db_session, RedditPost, id=post.id) == 0
    assert await count(db_session, MatchedPost, reddit_post_id=post.reddit_post_id) == 0
    assert await count(db_session, Match, watcher_id=watcher.id) == 0
    logged = (
        await db_session.execute(select(RejectionLog).where(RejectionLog.watcher_id == watcher.id))
    ).scalar_one()
    assert logged.title == "Selling my old couch"
    [stats] = await stats_for(db_session, watcher)
    assert (stats.reviewed, stats.confirmed) == (1, 0)


@pytest.mark.db
async def test_post_matching_one_watcher_and_not_another_stores_one_match(db_session, use_session):
    sub = unique_sub()
    user = await make_user(db_session)
    yes = await make_db_watcher(
        db_session, user, name="yes", intent_text="wants this", subreddits=[sub]
    )
    no = await make_db_watcher(
        db_session, user, name="no", intent_text="wants something else", subreddits=[sub]
    )
    post = await make_db_post(db_session, subreddit=sub)
    verifier = FakeVerifier(matching={"wants this"})

    await match.match_post({"verifier": verifier, "settings": fake_settings()}, str(post.id))

    assert await count(db_session, Match, watcher_id=yes.id) == 1
    assert await count(db_session, Match, watcher_id=no.id) == 0
    assert await count(db_session, RejectionLog, watcher_id=no.id) == 1
    for watcher in (yes, no):
        [stats] = await stats_for(db_session, watcher)
        assert stats.reviewed == 1


@pytest.mark.db
async def test_post_with_no_candidate_watchers_is_dropped_without_calling_the_llm(
    db_session, use_session
):
    post = await make_db_post(db_session, subreddit=unique_sub())
    verifier = FakeVerifier()

    confirmed = await match.match_post(
        {"verifier": verifier, "settings": fake_settings()}, str(post.id)
    )

    assert confirmed == 0
    assert verifier.calls == []
    assert await count(db_session, RedditPost, id=post.id) == 0


@pytest.mark.db
async def test_watcher_created_after_the_post_does_not_judge_it(db_session, use_session):
    sub = unique_sub()
    user = await make_user(db_session)
    now = datetime.now(UTC)
    await make_db_watcher(db_session, user, subreddits=[sub], created_at=now + timedelta(minutes=5))
    post = await make_db_post(db_session, subreddit=sub, posted_at=now)
    verifier = FakeVerifier()

    await match.match_post({"verifier": verifier, "settings": fake_settings()}, str(post.id))

    assert verifier.calls == []
    assert await count(db_session, RedditPost, id=post.id) == 0


@pytest.mark.db
async def test_large_candidate_set_is_split_into_batches(db_session, use_session):
    sub = unique_sub()
    user = await make_user(db_session)
    for index in range(5):
        await make_db_watcher(db_session, user, name=f"w{index}", subreddits=[sub])
    post = await make_db_post(db_session, subreddit=sub)
    verifier = FakeVerifier(matches=False)

    await match.match_post(
        {"verifier": verifier, "settings": fake_settings(MATCH_BATCH_SIZE=2)}, str(post.id)
    )

    assert len(verifier.calls) == 3  # 5 watchers, batch size 2 → 2 + 2 + 1


@pytest.mark.db
async def test_failed_batch_leaves_the_post_queued_with_a_backoff(db_session, use_session):
    sub = unique_sub()
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user, intent_text="boom", subreddits=[sub])
    post = await make_db_post(db_session, subreddit=sub)
    verifier = FakeVerifier(fail_on={"boom"})

    confirmed = await match.match_post(
        {"verifier": verifier, "settings": fake_settings()}, str(post.id)
    )

    assert confirmed == 0
    queued = await db_session.get(RedditPost, post.id)
    assert queued.attempts == 1
    assert queued.locked_until > datetime.now(UTC)
    assert await count(db_session, Match, watcher_id=watcher.id) == 0
    assert await stats_for(db_session, watcher) == []


@pytest.mark.db
async def test_post_that_keeps_failing_is_dropped_after_max_attempts(db_session, use_session):
    sub = unique_sub()
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user, intent_text="boom", subreddits=[sub])
    post = await make_db_post(db_session, subreddit=sub, attempts=4)  # this claim is attempt 5
    verifier = FakeVerifier(fail_on={"boom"})

    await match.match_post(
        {"verifier": verifier, "settings": fake_settings(MATCH_MAX_ATTEMPTS=5)}, str(post.id)
    )

    assert await count(db_session, RedditPost, id=post.id) == 0
    assert await count(db_session, Match, watcher_id=watcher.id) == 0


@pytest.mark.db
async def test_match_post_skips_a_post_that_is_already_gone(db_session, use_session):
    verifier = FakeVerifier()

    confirmed = await match.match_post(
        {"verifier": verifier, "settings": fake_settings()}, str(uuid.uuid4())
    )

    assert confirmed == 0
    assert verifier.calls == []


# --- backfill sweep ------------------------------------------------------------------------------


@pytest.mark.db
async def test_backfill_judges_a_stale_queued_post(db_session, use_session):
    sub = unique_sub()
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user, subreddits=[sub])
    await clear_queue(db_session)
    post = await make_db_post(db_session, subreddit=sub)
    verifier = FakeVerifier(matches=True)

    handled = await match.backfill({"verifier": verifier, "settings": fake_settings()})

    assert handled == 1
    assert await count(db_session, RedditPost, id=post.id) == 0
    assert await count(db_session, Match, watcher_id=watcher.id) == 1


@pytest.mark.db
async def test_backfill_leaves_a_fresh_post_for_its_own_job(db_session, use_session):
    sub = unique_sub()
    user = await make_user(db_session)
    await make_db_watcher(db_session, user, subreddits=[sub])
    await clear_queue(db_session)
    post = await make_db_post(db_session, subreddit=sub)
    verifier = FakeVerifier(matches=True)

    handled = await match.backfill(
        {"verifier": verifier, "settings": fake_settings(MATCH_BACKFILL_MIN_AGE_SECONDS=3600)}
    )

    assert handled == 0
    assert await count(db_session, RedditPost, id=post.id) == 1


@pytest.mark.db
async def test_backfill_drops_posts_that_exhausted_their_attempts(db_session, use_session):
    await clear_queue(db_session)
    post = await make_db_post(db_session, subreddit=unique_sub(), attempts=5)
    verifier = FakeVerifier()

    await match.backfill({"verifier": verifier, "settings": fake_settings()})

    assert await count(db_session, RedditPost, id=post.id) == 0
    assert verifier.calls == []


# --- catch-up ---------------------------------------------------------------------------------


class FakeWindowSource:
    """Returns a fixed list for every subreddit and records the window it was asked for."""

    def __init__(self, posts: list[dict], fail: bool = False) -> None:
        self.posts = posts
        self.fail = fail
        self.calls: list[tuple[str, datetime, int]] = []

    async def fetch_window(self, subreddit, since, limit):
        self.calls.append((subreddit, since, limit))
        if self.fail:
            raise RuntimeError("reddit is down")
        return self.posts

    async def close(self) -> None:
        pass


def reddit_post(suffix: str, posted_at: datetime | None, title: str = "Need a developer") -> dict:
    return {
        "reddit_post_id": suffix,
        "subreddit": "forhire",
        "title": title,
        "body": "",
        "author": "someone",
        "permalink": f"https://reddit.com/r/forhire/comments/{suffix}",
        "posted_at": posted_at,
    }


def catchup_ctx(verifier, source, **settings) -> dict:
    return {"verifier": verifier, "source": source, "settings": fake_settings(**settings)}


def unique_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.mark.db
async def test_catchup_judges_only_posts_made_before_the_watcher_existed(db_session, use_session):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    until = datetime.now(UTC)
    early = unique_id("early")
    source = FakeWindowSource(
        [
            reddit_post(early, until - timedelta(minutes=30)),
            reddit_post(unique_id("after"), until + timedelta(minutes=1)),  # the normal queue's job
            reddit_post(unique_id("untimed"), None),  # can't be placed relative to `until`
        ]
    )
    verifier = FakeVerifier(matches=True)

    confirmed = await match.catchup_watcher(
        catchup_ctx(verifier, source), str(watcher.id), ["forhire"], until.isoformat()
    )

    assert confirmed == 1
    assert [call[0] for call in source.calls] == ["forhire"]
    # The window is exactly the lookback before `until`.
    assert source.calls[0][1] == until - timedelta(minutes=60)
    [(_, posts)] = verifier.post_calls
    assert [reddit_id for reddit_id, _, _ in posts] == [early]
    assert await count(db_session, MatchedPost, reddit_post_id=early) == 1
    assert await count(db_session, Match, watcher_id=watcher.id) == 1


@pytest.mark.db
async def test_catchup_counts_and_samples_rejections(db_session, use_session):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    until = datetime.now(UTC)
    nope = unique_id("nope")
    source = FakeWindowSource([reddit_post(nope, until - timedelta(minutes=5), title="Selling")])

    confirmed = await match.catchup_watcher(
        catchup_ctx(FakeVerifier(matches=False), source),
        str(watcher.id),
        ["forhire"],
        until.isoformat(),
    )

    assert confirmed == 0
    assert await count(db_session, MatchedPost, reddit_post_id=nope) == 0
    logged = (
        await db_session.execute(select(RejectionLog).where(RejectionLog.watcher_id == watcher.id))
    ).scalar_one()
    assert logged.title == "Selling"
    [stats] = await stats_for(db_session, watcher)
    assert (stats.reviewed, stats.confirmed) == (1, 0)


@pytest.mark.db
async def test_catchup_is_capped_and_batched(db_session, use_session):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    until = datetime.now(UTC)
    source = FakeWindowSource(
        [reddit_post(unique_id(f"p{i}"), until - timedelta(minutes=i + 1)) for i in range(12)]
    )
    verifier = FakeVerifier(matches=False)

    await match.catchup_watcher(
        catchup_ctx(verifier, source, CATCHUP_MAX_POSTS=7, CATCHUP_BATCH_SIZE=3),
        str(watcher.id),
        ["forhire"],
        until.isoformat(),
    )

    assert [len(posts) for _, posts in verifier.post_calls] == [3, 3, 1]  # 7 posts, batches of 3


@pytest.mark.db
async def test_catchup_survives_a_failing_source_and_a_failing_verifier(db_session, use_session):
    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user, intent_text="boom")
    until = datetime.now(UTC)
    ctx_args = (str(watcher.id), ["forhire"], until.isoformat())

    assert (
        await match.catchup_watcher(
            catchup_ctx(FakeVerifier(), FakeWindowSource([], fail=True)), *ctx_args
        )
        == 0
    )
    failing = FakeWindowSource([reddit_post(unique_id("a"), until - timedelta(minutes=1))])
    assert (
        await match.catchup_watcher(catchup_ctx(FakeVerifier(fail_on={"boom"}), failing), *ctx_args)
        == 0
    )
    assert await count(db_session, Match, watcher_id=watcher.id) == 0


@pytest.mark.db
async def test_catchup_skips_a_paused_or_missing_watcher(db_session, use_session):
    user = await make_user(db_session)
    paused = await make_db_watcher(db_session, user, status="paused")
    source = FakeWindowSource([])
    until = datetime.now(UTC).isoformat()

    assert (
        await match.catchup_watcher(
            catchup_ctx(FakeVerifier(), source), str(paused.id), ["forhire"], until
        )
        == 0
    )
    assert (
        await match.catchup_watcher(
            catchup_ctx(FakeVerifier(), source), str(uuid.uuid4()), ["forhire"], until
        )
        == 0
    )
    assert source.calls == []


# --- storing outcomes ----------------------------------------------------------------------------


@pytest.mark.db
async def test_store_outcomes_is_idempotent_and_accumulates_stats(db_session):
    from app.workers.outcomes import Outcome, post_to_dict, store_outcomes

    user = await make_user(db_session)
    watcher = await make_db_watcher(db_session, user)
    post = await make_db_post(db_session)
    outcome = Outcome(watcher.id, post_to_dict(post), True, "yes", "m")

    first = await store_outcomes(db_session, [outcome, outcome])  # a repeated pair is collapsed
    second = await store_outcomes(db_session, [outcome])
    await db_session.commit()

    assert len(first) == 1
    assert second == []  # unique (watcher, post) pair: nothing new
    assert await count(db_session, Match, watcher_id=watcher.id) == 1
    assert await count(db_session, MatchedPost, reddit_post_id=post.reddit_post_id) == 1
    [stats] = await stats_for(db_session, watcher)
    assert (stats.reviewed, stats.confirmed) == (2, 2)
