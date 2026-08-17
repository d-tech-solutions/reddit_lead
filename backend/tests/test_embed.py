import uuid
from types import SimpleNamespace

import pytest

from app.models.reddit_post import RedditPost
from app.models.watcher import Watcher
from app.workers import embed
from tests.conftest import FakeEmbeddingProvider


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def make_post(reddit_post_id: str = "abc123", title: str = "Need a logo", body: str = "") -> RedditPost:
    post = RedditPost(
        reddit_post_id=reddit_post_id,
        subreddit="forhire",
        title=title,
        body=body,
        permalink="https://reddit.com/x",
    )
    # The matching hand-off reads post.id, which the DB would normally assign on flush.
    post.id = uuid.uuid4()
    return post


class FakeRedis:
    def __init__(self, failing: bool = False):
        self.jobs: list[tuple[str, str, str]] = []
        self.failing = failing

    async def enqueue_job(self, name, *args, _job_id=None):
        if self.failing:
            raise RuntimeError("redis is down")
        self.jobs.append((name, args[0], _job_id))


def make_watcher(intent_text: str = "people who need a logo designed") -> Watcher:
    return Watcher(
        name="logo work",
        intent_text=intent_text,
        subreddits=["forhire"],
        status="active",
    )


@pytest.fixture
def fake_settings():
    return SimpleNamespace(EMBEDDING_BATCH_SIZE=100, EMBED_BACKFILL_LIMIT=500)


async def test_embed_posts_writes_vector_and_timestamp(fake_provider, fake_settings):
    session = FakeSession()
    post = make_post()

    updated = await embed.embed_posts(session, fake_provider, [post], 100)

    assert updated == 1
    assert post.embedding is not None
    assert post.embedded_at is not None
    assert session.commits == 1


async def test_embed_posts_skips_rows_with_no_text(fake_provider):
    session = FakeSession()
    empty = make_post(reddit_post_id="empty", title="   ", body="")

    updated = await embed.embed_posts(session, fake_provider, [empty], 100)

    assert updated == 0
    assert empty.embedding is None
    # Nothing usable means no API call at all — the endpoint rejects empty input anyway.
    assert fake_provider.calls == []
    assert session.commits == 0


async def test_embed_posts_respects_batch_size(fake_provider):
    session = FakeSession()
    posts = [make_post(reddit_post_id=f"id{index}", title=f"post {index}") for index in range(5)]

    updated = await embed.embed_posts(session, fake_provider, posts, 2)

    assert updated == 5
    assert [len(call) for call in fake_provider.calls] == [2, 2, 1]


async def test_embed_posts_leaves_rows_unembedded_when_the_provider_fails():
    # The row must stay NULL so the backfill sweep retries it rather than losing it silently.
    session = FakeSession()
    post = make_post(title="Need a logo")
    provider = FakeEmbeddingProvider(fail_on={"Need a logo"})

    with pytest.raises(RuntimeError):
        await embed.embed_posts(session, provider, [post], 100)

    assert post.embedding is None
    assert session.commits == 0


async def test_embed_posts_uses_title_and_body_together(fake_provider):
    session = FakeSession()
    post = make_post(title="Need a logo", body="Budget is $200")

    await embed.embed_posts(session, fake_provider, [post], 100)

    assert fake_provider.calls == [["Need a logo\n\nBudget is $200"]]


async def test_embed_posts_enqueues_a_match_job_per_post(fake_provider):
    session = FakeSession()
    posts = [make_post(reddit_post_id="p1"), make_post(reddit_post_id="p2")]
    redis = FakeRedis()

    await embed.embed_posts(session, fake_provider, posts, 100, redis)

    assert [job[0] for job in redis.jobs] == ["match_post", "match_post"]
    assert all(job[2] == f"match_post:{job[1]}" for job in redis.jobs)


async def test_embed_posts_enqueues_only_after_committing(fake_provider):
    # The matcher loads the post by id, so a job sent before the commit could read a missing row.
    session = FakeSession()
    redis = FakeRedis()
    order: list[str] = []

    original_commit = session.commit

    async def tracking_commit():
        order.append("commit")
        await original_commit()

    session.commit = tracking_commit

    original_enqueue = redis.enqueue_job

    async def tracking_enqueue(name, *args, _job_id=None):
        order.append("enqueue")
        await original_enqueue(name, *args, _job_id=_job_id)

    redis.enqueue_job = tracking_enqueue

    await embed.embed_posts(session, fake_provider, [make_post()], 100, redis)

    assert order == ["commit", "enqueue"]


async def test_embedding_survives_a_failing_match_queue(fake_provider):
    # Embedding must not roll back because the next stage is unreachable; the matcher's own
    # backfill sweep recovers the missed job.
    session = FakeSession()
    post = make_post()

    updated = await embed.embed_posts(
        session, fake_provider, [post], 100, FakeRedis(failing=True)
    )

    assert updated == 1
    assert post.embedding is not None


async def test_enqueue_for_matching_without_redis_is_a_noop():
    await embed.enqueue_for_matching(None, [uuid.uuid4()])


async def test_embed_watchers_writes_intent_embedding(fake_provider):
    session = FakeSession()
    watcher = make_watcher()

    updated = await embed.embed_watchers(session, fake_provider, [watcher], 100)

    assert updated == 1
    assert watcher.intent_embedding is not None
    assert watcher.embedded_at is not None
    assert session.commits == 1


async def test_embed_watchers_skips_empty_intent_text(fake_provider):
    session = FakeSession()
    watcher = make_watcher(intent_text="   ")

    assert await embed.embed_watchers(session, fake_provider, [watcher], 100) == 0
    assert fake_provider.calls == []


async def test_backfill_embeds_both_watchers_and_posts(monkeypatch, fake_provider, fake_settings):
    posts = [make_post(reddit_post_id="p1"), make_post(reddit_post_id="p2")]
    watchers = [make_watcher()]

    async def fake_fetch_posts(session, limit):
        return posts

    async def fake_fetch_watchers(session, limit):
        return watchers

    monkeypatch.setattr(embed, "fetch_posts_needing_embedding", fake_fetch_posts)
    monkeypatch.setattr(embed, "fetch_watchers_needing_embedding", fake_fetch_watchers)
    monkeypatch.setattr(embed, "async_session_factory", _session_factory())

    total = await embed.backfill({"provider": fake_provider, "settings": fake_settings})

    assert total == 3
    assert all(post.embedding is not None for post in posts)
    assert watchers[0].intent_embedding is not None


async def test_backfill_does_nothing_when_everything_is_embedded(
    monkeypatch, fake_provider, fake_settings
):
    async def fake_fetch_none(session, limit):
        return []

    monkeypatch.setattr(embed, "fetch_posts_needing_embedding", fake_fetch_none)
    monkeypatch.setattr(embed, "fetch_watchers_needing_embedding", fake_fetch_none)
    monkeypatch.setattr(embed, "async_session_factory", _session_factory())

    assert await embed.backfill({"provider": fake_provider, "settings": fake_settings}) == 0
    assert fake_provider.calls == []


# Stand in for `async_session_factory`, which the worker uses as an async context manager.
def _session_factory():
    class Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, *exc_info):
            return False

    return Factory()


@pytest.mark.parametrize(
    ("interval", "expected_count", "expected_first"),
    [
        (5, 12, {0, 5, 10}),
        (1, 60, {0, 1, 2}),
        (15, 4, {0, 15, 30}),
        (60, 1, {0}),
    ],
)
def test_backfill_minutes_builds_an_even_schedule(interval, expected_count, expected_first):
    minutes = embed.backfill_minutes(interval)
    assert len(minutes) == expected_count
    assert expected_first.issubset(minutes)


@pytest.mark.parametrize("interval", [7, 13, 45, 0, -5, 999])
def test_backfill_minutes_falls_back_to_a_divisor_of_sixty(interval):
    minutes = embed.backfill_minutes(interval)
    assert 60 % (60 // len(minutes)) == 0
    assert 0 in minutes
