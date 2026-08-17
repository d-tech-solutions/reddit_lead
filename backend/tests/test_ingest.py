import uuid

import pytest

from app.workers import ingest


class FakeSource:
    def __init__(self, posts_by_subreddit: dict[str, list[dict]], failing: set[str] | None = None):
        self.posts_by_subreddit = posts_by_subreddit
        self.failing = failing or set()
        self.fetched: list[str] = []

    async def fetch(self, subreddit: str, limit: int) -> list[dict]:
        self.fetched.append(subreddit)
        if subreddit in self.failing:
            raise RuntimeError("reddit is down")
        return self.posts_by_subreddit.get(subreddit, [])

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

    async def enqueue_job(self, name, *args, _job_id=None):
        if self.failing:
            raise RuntimeError("redis is down")
        self.jobs.append((name, args[0], _job_id))


async def test_poll_once_enqueues_an_embed_job_per_new_post(monkeypatch, patched_ingest):
    _patch_subreddits(monkeypatch, ["forhire"])
    source = FakeSource({"forhire": [{"reddit_post_id": "a"}, {"reddit_post_id": "b"}]})
    redis = FakeRedis()

    await ingest.poll_once(session=None, source=source, redis=redis)

    assert [job[0] for job in redis.jobs] == ["embed_post", "embed_post"]
    # The job id is derived from the post id so a duplicate enqueue is a no-op.
    assert all(job[2] == f"embed_post:{job[1]}" for job in redis.jobs)


async def test_enqueue_for_embedding_without_redis_is_a_noop():
    await ingest.enqueue_for_embedding(None, [uuid.uuid4()])


async def test_ingestion_survives_a_failing_queue(monkeypatch, patched_ingest):
    # Storing posts must succeed even when the queue is unreachable; the embed worker's backfill
    # sweep is what recovers the missed jobs.
    _patch_subreddits(monkeypatch, ["forhire"])
    source = FakeSource({"forhire": [{"reddit_post_id": "a"}]})

    new_count = await ingest.poll_once(session=None, source=source, redis=FakeRedis(failing=True))

    assert new_count == 1
    assert len(patched_ingest) == 1
