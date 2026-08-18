import uuid

import pytest

from app.workers.verifier import (
    MAX_POST_CHARS,
    SYSTEM_PROMPT,
    Verdict,
    apply_candidate_numbers,
    build_prompt,
    build_verifier,
)

WATCHER_A = uuid.uuid4()
WATCHER_B = uuid.uuid4()


def test_build_verifier_requires_an_api_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_verifier("", "gpt-4o-mini")


def test_build_verifier_returns_a_verifier_when_configured():
    verifier = build_verifier("sk-not-a-real-key", "gpt-4o-mini")
    assert hasattr(verifier, "verify_batch")


def test_build_prompt_numbers_every_candidate():
    prompt = build_prompt(
        "Need a dev",
        "Budget $500",
        [(WATCHER_A, "people hiring developers"), (WATCHER_B, "developers for hire")],
    )
    assert "Candidate 1: people hiring developers" in prompt
    assert "Candidate 2: developers for hire" in prompt


def test_build_prompt_includes_the_post():
    prompt = build_prompt("Need a dev", "Budget $500", [(WATCHER_A, "intent")])
    assert "Need a dev" in prompt
    assert "Budget $500" in prompt


def test_build_prompt_handles_an_empty_body():
    # RSS mode supplies no body, so title-only must not leave a dangling separator.
    prompt = build_prompt("Just a title", "", [(WATCHER_A, "intent")])
    assert "Just a title\n--- END POST ---" in prompt


def test_build_prompt_truncates_a_long_post():
    prompt = build_prompt("T", "x" * (MAX_POST_CHARS * 2), [(WATCHER_A, "intent")])
    assert len(prompt) < MAX_POST_CHARS + 500


def test_system_prompt_covers_direction_subject_and_substance():
    # These three checks are the whole reason this stage exists; losing one silently would let the
    # needs-vs-offers failure back in.
    lowered = SYSTEM_PROMPT.lower()
    assert "direction" in lowered
    assert "opposite side of the transaction" in lowered
    assert "subject" in lowered
    assert "substance" in lowered


def test_system_prompt_covers_the_neutral_direction_case():
    # A topic-only watcher (no request/offer implied) must not be direction-gated.
    assert "neither" in SYSTEM_PROMPT.lower()


def test_system_prompt_tells_the_model_to_ignore_tags():
    # Posters mislabel their own posts, so tag formatting must not drive the verdict.
    assert "tags or title formatting" in SYSTEM_PROMPT


def test_system_prompt_biases_towards_false_when_unsure():
    assert "ties go to false" in SYSTEM_PROMPT


def test_apply_candidate_numbers_maps_back_to_watcher_ids():
    candidates = [(WATCHER_A, "intent a"), (WATCHER_B, "intent b")]
    raw = [
        {"candidate_number": 1, "matches": True, "reasoning": "yes"},
        {"candidate_number": 2, "matches": False, "reasoning": "no"},
    ]

    verdicts = apply_candidate_numbers(raw, candidates, "m")

    assert verdicts[0] == Verdict(watcher_id=WATCHER_A, matches=True, reason="yes", model="m")
    assert verdicts[1] == Verdict(watcher_id=WATCHER_B, matches=False, reason="no", model="m")


def test_apply_candidate_numbers_skips_an_out_of_range_number():
    candidates = [(WATCHER_A, "intent a")]
    raw = [{"candidate_number": 5, "matches": True, "reasoning": "?"}]

    assert apply_candidate_numbers(raw, candidates, "m") == []


def test_apply_candidate_numbers_skips_a_non_integer_number():
    candidates = [(WATCHER_A, "intent a")]
    raw = [{"candidate_number": "one", "matches": True, "reasoning": "?"}]

    assert apply_candidate_numbers(raw, candidates, "m") == []


def test_apply_candidate_numbers_truncates_a_rambling_reason():
    candidates = [(WATCHER_A, "intent a")]
    raw = [{"candidate_number": 1, "matches": True, "reasoning": "x" * 2000}]

    verdicts = apply_candidate_numbers(raw, candidates, "m")

    assert len(verdicts[0].reason) == 500


def test_apply_candidate_numbers_defaults_a_missing_matches_field_to_false():
    candidates = [(WATCHER_A, "intent a")]
    raw = [{"candidate_number": 1, "reasoning": "no matches field"}]

    verdicts = apply_candidate_numbers(raw, candidates, "m")

    assert verdicts[0].matches is False


def test_apply_candidate_numbers_handles_fewer_verdicts_than_candidates():
    # The model skipping a candidate is not fatal here — the caller leaves that row NULL for the
    # backfill sweep, rather than fabricating a verdict.
    candidates = [(WATCHER_A, "a"), (WATCHER_B, "b")]
    raw = [{"candidate_number": 1, "matches": True, "reasoning": "only this one"}]

    verdicts = apply_candidate_numbers(raw, candidates, "m")

    assert len(verdicts) == 1
    assert verdicts[0].watcher_id == WATCHER_A
