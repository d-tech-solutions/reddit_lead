import math

import pytest

from app.workers import direction
from app.workers.direction import (
    OFFER_PHRASINGS,
    REQUEST_PHRASINGS,
    compute_direction_axis,
    direction_penalty,
    direction_score,
    mean_vector,
    normalise,
)


def test_normalise_returns_unit_length():
    result = normalise([3.0, 4.0])
    assert math.isclose(math.sqrt(sum(v * v for v in result)), 1.0)


def test_normalise_leaves_the_zero_vector_alone():
    # A zero vector has no direction; dividing by its length would raise.
    assert normalise([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]


def test_mean_vector_averages_componentwise():
    assert mean_vector([[0.0, 2.0], [2.0, 4.0]]) == [1.0, 3.0]


async def test_compute_direction_axis_embeds_every_phrasing(fake_provider):
    axis = await compute_direction_axis(fake_provider)

    sent = fake_provider.calls[0]
    assert sent == REQUEST_PHRASINGS + OFFER_PHRASINGS
    assert math.isclose(math.sqrt(sum(v * v for v in axis)), 1.0, rel_tol=1e-6)


async def test_direction_axis_is_deterministic(fake_provider):
    first = await compute_direction_axis(fake_provider)
    second = await compute_direction_axis(fake_provider)

    # Scores must be comparable across worker restarts, so the axis cannot drift.
    assert first == second


def test_direction_score_is_positive_along_the_axis():
    axis = normalise([1.0, 0.0])
    assert direction_score([5.0, 0.0], axis) == pytest.approx(1.0)
    assert direction_score([-5.0, 0.0], axis) == pytest.approx(-1.0)
    assert direction_score([0.0, 5.0], axis) == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("score", "watcher_direction", "expected"),
    [
        # A watcher wanting requests is penalised for offer-leaning posts, and only those.
        (0.08, "requesting", 0.08),
        (-0.08, "requesting", 0.0),
        # A watcher wanting offers is penalised the other way round.
        (-0.08, "offering", 0.08),
        (0.08, "offering", 0.0),
        (0.0, "requesting", 0.0),
    ],
)
def test_direction_penalty_is_one_sided(score, watcher_direction, expected):
    assert direction_penalty(score, watcher_direction) == pytest.approx(expected)


def test_direction_penalty_never_rewards_the_right_direction():
    # A bonus for pointing the right way would let a topically irrelevant post outrank a
    # well-matched one — the mirror of the bug this axis exists to fix.
    for score in (-1.0, -0.5, 0.0, 0.5, 1.0):
        assert direction_penalty(score, "requesting") >= 0.0
        assert direction_penalty(score, "offering") >= 0.0


def test_phrasings_mention_no_specific_trade():
    # The axis must encode direction only. A job title or skill here would leak topic into it and
    # let it penalise genuine matches on that topic.
    topical = ["developer", "designer", "marketer", "logo", "python", "react", "writer"]
    for phrase in REQUEST_PHRASINGS + OFFER_PHRASINGS:
        lowered = phrase.lower()
        assert not any(word in lowered for word in topical), phrase


def test_both_phrasing_groups_are_balanced():
    assert len(REQUEST_PHRASINGS) == len(OFFER_PHRASINGS)


def test_dot_requires_equal_lengths():
    with pytest.raises(ValueError):
        direction.dot([1.0, 2.0], [1.0])
