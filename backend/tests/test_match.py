import uuid
from types import SimpleNamespace

import pytest

from app.models.match import Match
from app.models.reddit_post import RedditPost
from app.models.watcher import Watcher
from app.workers import match
from app.workers.direction import normalise
from tests.conftest import FakeVerifier

# A 2-D world keeps the arithmetic readable: x is the "developer work" topic axis, y is direction.
AXIS = normalise([0.0, 1.0])


def make_post(
    reddit_post_id: str = "abc123",
    subreddit: str = "forhire",
    title: str = "Need a developer",
    body: str = "",
    embedding: list[float] | None = None,
) -> RedditPost:
    post = RedditPost(
        reddit_post_id=reddit_post_id,
        subreddit=subreddit,
        title=title,
        body=body,
        permalink="https://reddit.com/x",
    )
    post.id = uuid.uuid4()
    post.embedding = embedding if embedding is not None else [1.0, 0.0]
    return post


def make_watcher(
    name: str = "dev hiring",
    intent_text: str = "someone looking to hire a developer",
    direction: str = "requesting",
    subreddits: list[str] | None = None,
    embedding: list[float] | None = None,
) -> Watcher:
    watcher = Watcher(
        name=name,
        intent_text=intent_text,
        subreddits=subreddits if subreddits is not None else ["forhire"],
        status="active",
        direction=direction,
    )
    watcher.id = uuid.uuid4()
    watcher.intent_embedding = embedding if embedding is not None else [1.0, 0.0]
    return watcher


@pytest.fixture
def fake_settings():
    return SimpleNamespace(
        MATCH_TOP_K=10,
        MATCH_DIRECTION_WEIGHT=1.0,
        MATCH_BACKFILL_LIMIT=200,
    )


def test_cosine_of_identical_vectors_is_one():
    assert match.cosine([1.0, 2.0], [1.0, 2.0]) == pytest.approx(1.0)


def test_cosine_ignores_magnitude():
    assert match.cosine([1.0, 0.0], [7.0, 0.0]) == pytest.approx(1.0)


def test_cosine_of_orthogonal_vectors_is_zero():
    assert match.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_handles_a_zero_vector():
    # An unembedded row should score neutrally rather than raise a division error.
    assert match.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_rank_watchers_orders_by_adjusted_score():
    close = make_watcher(name="close", embedding=[1.0, 0.0])
    far = make_watcher(name="far", embedding=[0.3, 0.95])
    post = make_post(embedding=[1.0, 0.0])

    ranked = match.rank_watchers(post.embedding, [far, close], AXIS, 1.0, 10)

    assert [row[0].name for row in ranked] == ["close", "far"]


def test_rank_watchers_respects_top_k():
    watchers = [make_watcher(name=f"w{i}") for i in range(5)]
    post = make_post()

    ranked = match.rank_watchers(post.embedding, watchers, AXIS, 1.0, 2)

    assert len(ranked) == 2


def test_rank_watchers_penalises_a_wrong_direction_post():
    # The post leans "offer" (positive on the direction axis); the watcher wants requests.
    watcher = make_watcher(direction="requesting", embedding=[1.0, 0.0])
    offer_post = make_post(embedding=normalise([1.0, 0.5]))

    ranked = match.rank_watchers(offer_post.embedding, [watcher], AXIS, 1.0, 10)
    _, similarity, post_direction, adjusted = ranked[0]

    assert post_direction > 0
    assert adjusted < similarity


def test_rank_watchers_separates_opposite_direction_watchers():
    # This is what the penalty is actually for: one post, two watchers wanting opposite sides.
    wants_requests = make_watcher(name="wants-requests", direction="requesting")
    wants_offers = make_watcher(name="wants-offers", direction="offering")
    offer_post = make_post(embedding=normalise([1.0, 0.5]))

    ranked = match.rank_watchers(offer_post.embedding, [wants_requests, wants_offers], AXIS, 1.0, 10)

    assert ranked[0][0].name == "wants-offers"


def test_rank_watchers_does_not_reorder_same_direction_watchers():
    # The penalty is constant across watchers wanting the same side, so it cannot rerank them —
    # its job there is to push the whole set down, not to shuffle it.
    a = make_watcher(name="a", embedding=[1.0, 0.0])
    b = make_watcher(name="b", embedding=normalise([0.9, 0.1]))
    offer_post = make_post(embedding=normalise([1.0, 0.5]))

    unpenalised = match.rank_watchers(offer_post.embedding, [a, b], AXIS, 0.0, 10)
    penalised = match.rank_watchers(offer_post.embedding, [a, b], AXIS, 1.0, 10)

    assert [row[0].name for row in unpenalised] == [row[0].name for row in penalised]


def test_rank_watchers_with_zero_weight_is_plain_similarity():
    watcher = make_watcher()
    post = make_post(embedding=normalise([1.0, 0.5]))

    ranked = match.rank_watchers(post.embedding, [watcher], AXIS, 0.0, 10)
    _, similarity, _, adjusted = ranked[0]

    assert adjusted == pytest.approx(similarity)


def test_rank_watchers_with_no_watchers_returns_nothing():
    assert match.rank_watchers([1.0, 0.0], [], AXIS, 1.0, 10) == []


class FakeSession:
    """Minimal stand-in for AsyncSession covering only what the matcher calls."""

    def __init__(self, rows: dict | None = None) -> None:
        self.rows = rows or {}
        self.commits = 0

    async def get(self, model, row_id):
        return self.rows.get(row_id)

    async def commit(self) -> None:
        self.commits += 1


async def test_verify_candidate_records_a_positive_verdict(fake_verifier):
    watcher = make_watcher()
    post = make_post()
    candidate = Match(
        watcher_id=watcher.id,
        reddit_post_id=post.id,
        similarity=0.6,
        direction_score=-0.02,
        adjusted_score=0.6,
    )
    candidate.id = uuid.uuid4()
    session = FakeSession({candidate.id: candidate, watcher.id: watcher, post.id: post})

    result = await match.verify_candidate(session, fake_verifier, candidate.id)

    assert result is True
    assert candidate.llm_verified is True
    assert candidate.llm_reason == "fake verdict"
    assert candidate.llm_model == "fake-model"
    assert candidate.verified_at is not None
    assert session.commits == 1


async def test_verify_candidate_records_a_negative_verdict():
    watcher = make_watcher()
    post = make_post()
    candidate = Match(
        watcher_id=watcher.id,
        reddit_post_id=post.id,
        similarity=0.6,
        direction_score=0.05,
        adjusted_score=0.55,
    )
    candidate.id = uuid.uuid4()
    session = FakeSession({candidate.id: candidate, watcher.id: watcher, post.id: post})

    result = await match.verify_candidate(session, FakeVerifier(matches=False), candidate.id)

    # False is a real verdict, not a missing one — the row must not stay NULL.
    assert result is False
    assert candidate.llm_verified is False


async def test_verify_candidate_passes_the_watchers_direction_through(fake_verifier):
    watcher = make_watcher(direction="offering")
    post = make_post()
    candidate = Match(
        watcher_id=watcher.id,
        reddit_post_id=post.id,
        similarity=0.6,
        direction_score=0.0,
        adjusted_score=0.6,
    )
    candidate.id = uuid.uuid4()
    session = FakeSession({candidate.id: candidate, watcher.id: watcher, post.id: post})

    await match.verify_candidate(session, fake_verifier, candidate.id)

    assert fake_verifier.calls[0][1] == "offering"


async def test_verify_candidate_skips_an_already_judged_row(fake_verifier):
    watcher = make_watcher()
    post = make_post()
    candidate = Match(
        watcher_id=watcher.id,
        reddit_post_id=post.id,
        similarity=0.6,
        direction_score=0.0,
        adjusted_score=0.6,
    )
    candidate.id = uuid.uuid4()
    candidate.llm_verified = False
    session = FakeSession({candidate.id: candidate, watcher.id: watcher, post.id: post})

    assert await match.verify_candidate(session, fake_verifier, candidate.id) is None
    assert fake_verifier.calls == []


async def test_verify_candidate_leaves_the_row_unjudged_when_the_api_fails():
    watcher = make_watcher(intent_text="boom")
    post = make_post()
    candidate = Match(
        watcher_id=watcher.id,
        reddit_post_id=post.id,
        similarity=0.6,
        direction_score=0.0,
        adjusted_score=0.6,
    )
    candidate.id = uuid.uuid4()
    session = FakeSession({candidate.id: candidate, watcher.id: watcher, post.id: post})
    verifier = FakeVerifier(fail_on={"boom"})

    with pytest.raises(RuntimeError):
        await match.verify_candidate(session, verifier, candidate.id)

    # NULL is what the backfill sweep looks for, so it must survive the failure.
    assert candidate.llm_verified is None
    assert session.commits == 0


async def test_verify_candidate_skips_a_match_with_a_missing_watcher(fake_verifier):
    post = make_post()
    candidate = Match(
        watcher_id=uuid.uuid4(),
        reddit_post_id=post.id,
        similarity=0.6,
        direction_score=0.0,
        adjusted_score=0.6,
    )
    candidate.id = uuid.uuid4()
    session = FakeSession({candidate.id: candidate, post.id: post})

    assert await match.verify_candidate(session, fake_verifier, candidate.id) is None


async def test_gate_post_with_no_matching_watchers_writes_nothing(monkeypatch, fake_settings):
    async def no_watchers(session, subreddit):
        return []

    monkeypatch.setattr(match, "fetch_candidate_watchers", no_watchers)
    stored = []

    async def fake_store(session, post_id, ranked):
        stored.append(ranked)
        return []

    monkeypatch.setattr(match, "store_candidates", fake_store)

    result = await match.gate_post(FakeSession(), make_post(), AXIS, fake_settings)

    assert result == []
    assert stored == []


async def test_gate_post_stores_ranked_candidates(monkeypatch, fake_settings):
    watchers = [make_watcher(name="a"), make_watcher(name="b")]
    captured = {}

    async def fake_fetch(session, subreddit):
        captured["subreddit"] = subreddit
        return watchers

    async def fake_store(session, post_id, ranked):
        captured["ranked"] = ranked
        return [uuid.uuid4() for _ in ranked]

    monkeypatch.setattr(match, "fetch_candidate_watchers", fake_fetch)
    monkeypatch.setattr(match, "store_candidates", fake_store)

    result = await match.gate_post(
        FakeSession(), make_post(subreddit="slavelabour"), AXIS, fake_settings
    )

    assert captured["subreddit"] == "slavelabour"
    assert len(captured["ranked"]) == 2
    assert len(result) == 2


@pytest.mark.parametrize(
    ("interval", "expected_count"),
    [(5, 12), (1, 60), (15, 4), (60, 1), (7, 10), (0, 60)],
)
def test_backfill_minutes_builds_an_even_schedule(interval, expected_count):
    minutes = match.backfill_minutes(interval)
    assert len(minutes) == expected_count
    assert 0 in minutes
