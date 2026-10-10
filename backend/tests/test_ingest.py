import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import MATCH_QUEUE
from app.models.reddit_post import RedditPost
from app.models.seen_post import SeenPost
from app.models.user import User
from app.models.watcher import Watcher
from app.workers import ingest


class FakeSource:
    def __init__(self, posts_by_subreddit: dict[str, list[dict]], failing: set[str] | None = None):
        self.posts_by_subreddit = posts_by_subreddit
        self.failing = failing or set()
        self.fetched: list[str] = []
        self.windows: list[tuple[str, datetime, int]] = []

    async def fetch(self, subreddit: str, limit: int) -> list[dict]:
        self.fetched.append(subreddit)
        if subreddit in self.failing:
            raise RuntimeError("reddit is down")
        return self.posts_by_subreddit.get(subreddit, [])

    async def fetch_window(self, subreddit: str, since: datetime, limit: int) -> list[dict]:
        self.windows.append((subreddit, since, limit))
        return await self.fetch(subreddit, limit)

    async def close(self) -> None:
        pass


@pytest.fixture
def patched_ingest(monkeypatch):
    stored: list[dict] = []

    async def fake_store_posts(session, posts):
        stored.extend(posts)
        return [uuid.uuid4() for _ in posts]

    monkeypatch.setattr(ingest, "store_posts", fake_store_posts)
    return stored


def _patch_subreddits(monkeypatch, subreddits: list[str]):
    async def fake_get_active_subreddits(session):
        return subreddits

    monkeypatch.setattr(ingest, "get_active_subreddits", fake_get_active_subreddits)


async def test_poll_once_fetches_every_active_subreddit(monkeypatch, patched_ingest):
    _patch_subreddits(monkeypatch, ["forhire", "slavelabour"])
    source = FakeSource({"forhire": [{"reddit_post_id": "a"}], "slavelabour": [{"reddit_post_id": "b"}]})

    new_count = await ingest.poll_once(session=None, source=source)

    assert source.fetched == ["forhire", "slavelabour"]
    assert new_count == 2
    assert len(patched_ingest) == 2


async def test_poll_once_continues_after_one_subreddit_fails(monkeypatch, patched_ingest):
    _patch_subreddits(monkeypatch, ["broken", "working"])
    source = FakeSource({"working": [{"reddit_post_id": "a"}]}, failing={"broken"})

    new_count = await ingest.poll_once(session=None, source=source)

    assert source.fetched == ["broken", "working"]
    assert new_count == 1


async def test_poll_once_with_no_active_watchers_does_not_fetch(monkeypatch, patched_ingest):
    _patch_subreddits(monkeypatch, [])
    source = FakeSource({})

    assert await ingest.poll_once(session=None, source=source) == 0
    assert source.fetched == []


class FakeRedis:
    def __init__(self, failing: bool = False):
        self.jobs: list[tuple[str, str, str]] = []
        self.failing = failing
        self.queues: list[str | None] = []

    async def enqueue_job(self, name, *args, _job_id=None, _queue_name=None):
        if self.failing:
            raise RuntimeError("redis is down")
        self.jobs.append((name, args[0], _job_id))
        self.queues.append(_queue_name)


async def test_poll_once_enqueues_a_match_job_per_new_post(monkeypatch, patched_ingest):
    _patch_subreddits(monkeypatch, ["forhire"])
    source = FakeSource({"forhire": [{"reddit_post_id": "a"}, {"reddit_post_id": "b"}]})
    redis = FakeRedis()

    await ingest.poll_once(session=None, source=source, redis=redis)

    assert [job[0] for job in redis.jobs] == ["match_post", "match_post"]
    # The job id is derived from the post id so a duplicate enqueue is a no-op.
    assert all(job[2] == f"match_post:{job[1]}" for job in redis.jobs)
    assert redis.queues == [MATCH_QUEUE, MATCH_QUEUE]


async def test_enqueue_for_matching_without_redis_is_a_noop():
    await ingest.enqueue_for_matching(None, [uuid.uuid4()])


async def test_ingestion_survives_a_failing_queue(monkeypatch, patched_ingest):
    # Storing posts must succeed even when the queue is unreachable; the matcher's backfill sweep
    # is what recovers the missed jobs.
    _patch_subreddits(monkeypatch, ["forhire"])
    source = FakeSource({"forhire": [{"reddit_post_id": "a"}]})

    new_count = await ingest.poll_once(session=None, source=source, redis=FakeRedis(failing=True))

    assert new_count == 1
    assert len(patched_ingest) == 1


async def test_poll_once_asks_for_the_freshness_window_only(monkeypatch, patched_ingest):
    _patch_subreddits(monkeypatch, ["forhire"])
    source = FakeSource({"forhire": []})

    await ingest.poll_once(session=None, source=source)

    [(subreddit, since, limit)] = source.windows
    assert subreddit == "forhire"
    # One hour back (the configured look-back), not "the latest N posts whenever they were made".
    assert datetime.now(UTC) - since == pytest.approx(timedelta(minutes=60), abs=timedelta(seconds=5))
    assert limit == ingest.get_settings().INGEST_MAX_POSTS_PER_POLL


# --- freshness filter (no DB) ---------------------------------------------------------------------


def test_drop_stale_posts_removes_old_posts_and_stamps_untimed_ones():
    now = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    posts = [
        {"reddit_post_id": "fresh", "posted_at": now - timedelta(minutes=10)},
        {"reddit_post_id": "stale", "posted_at": now - timedelta(minutes=61)},
        {"reddit_post_id": "untimed", "posted_at": None},
    ]

    kept = ingest.drop_stale_posts(posts, timedelta(minutes=60), now=now)

    assert [post["reddit_post_id"] for post in kept] == ["fresh", "untimed"]
    assert kept[1]["posted_at"] == now
    assert posts[2]["posted_at"] is None  # the input is not mutated


# --- store_posts + get_active_subreddits (real SQL) ----------------------------------------------


def _post(reddit_post_id: str, posted_at: datetime | None = None, subreddit: str = "forhire") -> dict:
    return {
        "reddit_post_id": reddit_post_id,
        "subreddit": subreddit,
        "title": "Need a dev",
        "body": "",
        "author": "someone",
        "permalink": f"https://reddit.com/r/{subreddit}/comments/{reddit_post_id}",
        "posted_at": posted_at or datetime.now(UTC),
    }


@pytest.mark.db
async def test_store_posts_queues_new_posts_and_remembers_their_ids(db_session):
    new_ids = await ingest.store_posts(db_session, [_post("aaa"), _post("bbb")])

    assert len(new_ids) == 2
    queued = (await db_session.execute(select(RedditPost.reddit_post_id))).scalars().all()
    assert set(queued) >= {"aaa", "bbb"}
    seen = (await db_session.execute(select(SeenPost.reddit_post_id))).scalars().all()
    assert set(seen) >= {"aaa", "bbb"}


@pytest.mark.db
async def test_store_posts_never_requeues_a_post_deleted_after_judging(db_session):
    [post_id] = await ingest.store_posts(db_session, [_post("once")])
    # The matcher deletes a judged post from the queue; its id stays in seen_posts.
    await db_session.delete(await db_session.get(RedditPost, post_id))
    await db_session.commit()

    again = await ingest.store_posts(db_session, [_post("once")])

    assert again == []
    count = await db_session.execute(
        select(func.count()).select_from(RedditPost).where(RedditPost.reddit_post_id == "once")
    )
    assert count.scalar_one() == 0


@pytest.mark.db
async def test_store_posts_drops_stale_posts_and_in_batch_duplicates(db_session):
    stale = _post("stale", posted_at=datetime.now(UTC) - timedelta(hours=3))

    new_ids = await ingest.store_posts(db_session, [stale, _post("dup"), _post("dup")])

    assert len(new_ids) == 1
    seen = (await db_session.execute(select(SeenPost.reddit_post_id))).scalars().all()
    assert "stale" not in seen


@pytest.mark.db
async def test_get_active_subreddits_is_distinct_and_ignores_paused_watchers(db_session):
    user = User(clerk_user_id=f"user_test_{uuid.uuid4().hex[:12]}")
    db_session.add(user)
    await db_session.commit()
    unique = f"s{uuid.uuid4().hex[:10]}"
    for subreddits, status in [([unique, "forhire"], "active"), ([unique], "active"), (["paused_only_sub"], "paused")]:
        db_session.add(
            Watcher(user_id=user.id, name="w", intent_text="x", subreddits=subreddits, status=status)
        )
    await db_session.commit()

    active = await ingest.get_active_subreddits(db_session)

    assert active.count(unique) == 1
    assert "paused_only_sub" not in active
