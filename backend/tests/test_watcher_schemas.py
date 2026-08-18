import pytest
from pydantic import ValidationError

from app.schemas.watcher import (
    MIN_INTENT_CHARS,
    WatcherCreate,
    WatcherUpdate,
    normalise_subreddit,
    normalise_subreddits,
)

VALID_INTENT = "someone looking to hire a developer for a web project"


@pytest.mark.parametrize(
    "raw",
    ["forhire", "r/forhire", "/r/forhire", "R/ForHire", "ForHire", " r/forhire ", "r/forhire/"],
)
def test_subreddit_normalisation_collapses_every_spelling(raw):
    # Casing is not cosmetic here: the ingestion worker polls these strings and the matcher does an
    # exact-string comparison against them, so two spellings would double-poll and half-match.
    assert normalise_subreddit(raw) == "forhire"


@pytest.mark.parametrize("raw", ["ab", "a" * 22, "for hire", "for-hire", "r/", "", "for.hire"])
def test_invalid_subreddit_names_are_rejected(raw):
    with pytest.raises(ValueError):
        normalise_subreddit(raw)


def test_underscores_and_digits_are_allowed():
    assert normalise_subreddit("r/web_dev2") == "web_dev2"


def test_duplicate_subreddits_are_dropped_preserving_order():
    assert normalise_subreddits(["r/ForHire", "slavelabour", "forhire"]) == [
        "forhire",
        "slavelabour",
    ]


def test_create_normalises_subreddits():
    payload = WatcherCreate(
        name="devs", intent_text=VALID_INTENT, subreddits=["r/ForHire", "/r/JobsHiring"]
    )
    assert payload.subreddits == ["forhire", "jobshiring"]


def test_create_defaults_status():
    payload = WatcherCreate(name="devs", intent_text=VALID_INTENT, subreddits=["forhire"])
    assert payload.status == "active"


def test_create_strips_whitespace():
    payload = WatcherCreate(
        name="  devs  ", intent_text=f"  {VALID_INTENT}  ", subreddits=["forhire"]
    )
    assert payload.name == "devs"
    assert payload.intent_text == VALID_INTENT


def test_short_intent_is_rejected():
    # A three-word intent produces a vector that matches almost anything.
    with pytest.raises(ValidationError):
        WatcherCreate(name="devs", intent_text="devs", subreddits=["forhire"])


def test_intent_at_the_minimum_length_is_accepted():
    WatcherCreate(name="devs", intent_text="x" * MIN_INTENT_CHARS, subreddits=["forhire"])


def test_empty_subreddit_list_is_rejected():
    with pytest.raises(ValidationError):
        WatcherCreate(name="devs", intent_text=VALID_INTENT, subreddits=[])


def test_unknown_status_is_rejected():
    with pytest.raises(ValidationError):
        WatcherCreate(
            name="devs", intent_text=VALID_INTENT, subreddits=["forhire"], status="archived"
        )


def test_update_defaults_everything_to_none():
    # None means "leave alone" on a PATCH, so every field must default to it.
    payload = WatcherUpdate()
    assert payload.model_dump(exclude_unset=True) == {}
    assert payload.subreddits is None
    assert payload.intent_text is None


def test_update_normalises_subreddits_when_given():
    payload = WatcherUpdate(subreddits=["R/ForHire"])
    assert payload.subreddits == ["forhire"]


def test_update_still_rejects_a_short_intent():
    with pytest.raises(ValidationError):
        WatcherUpdate(intent_text="nope")
