import pytest

from app.workers.verifier import (
    MAX_POST_CHARS,
    SYSTEM_PROMPT,
    build_prompt,
    build_verifier,
    parse_verdict,
)


def test_build_verifier_requires_an_api_key():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_verifier("", "claude-haiku-4-5")


def test_build_verifier_returns_a_verifier_when_configured():
    verifier = build_verifier("sk-ant-not-a-real-key", "claude-haiku-4-5")
    assert hasattr(verifier, "verify")


def test_build_prompt_states_the_wanted_direction():
    requesting = build_prompt("people hiring developers", "requesting", "T", "B")
    offering = build_prompt("developers for hire", "offering", "T", "B")

    assert "REQUESTING work" in requesting
    assert "OFFERING their services" in offering


def test_build_prompt_includes_intent_and_post():
    prompt = build_prompt("people hiring developers", "requesting", "Need a dev", "Budget $500")

    assert "people hiring developers" in prompt
    assert "Need a dev" in prompt
    assert "Budget $500" in prompt


def test_build_prompt_handles_an_empty_body():
    # RSS mode supplies no body, so title-only must not leave a dangling separator.
    prompt = build_prompt("intent", "requesting", "Just a title", "")
    assert "Just a title\n--- END POST ---" in prompt


def test_build_prompt_truncates_long_posts():
    prompt = build_prompt("intent", "requesting", "T", "x" * (MAX_POST_CHARS * 2))
    assert len(prompt) < MAX_POST_CHARS + 500


def test_system_prompt_covers_direction_subject_and_substance():
    # These three checks are the whole reason this stage exists; losing one silently would let the
    # needs-vs-offers failure back in.
    lowered = SYSTEM_PROMPT.lower()
    assert "direction" in lowered
    assert "opposite side of the transaction" in lowered
    assert "subject" in lowered
    assert "substance" in lowered


def test_system_prompt_tells_the_model_to_ignore_tags():
    # Posters mislabel their own posts, so tag formatting must not drive the verdict.
    assert "tags or title formatting" in SYSTEM_PROMPT


def test_system_prompt_biases_towards_false_when_unsure():
    assert "too vague to tell, answer false" in SYSTEM_PROMPT


def test_parse_verdict_reads_a_plain_object():
    verdict = parse_verdict('{"matches": true, "reason": "hiring a dev"}', "m")

    assert verdict.matches is True
    assert verdict.reason == "hiring a dev"
    assert verdict.model == "m"


def test_parse_verdict_tolerates_surrounding_prose():
    # A parse failure would discard a decision the model actually made, so be forgiving.
    verdict = parse_verdict('Here is my answer:\n{"matches": false, "reason": "offer"}\n', "m")

    assert verdict.matches is False
    assert verdict.reason == "offer"


def test_parse_verdict_tolerates_a_code_fence():
    verdict = parse_verdict('```json\n{"matches": true, "reason": "ok"}\n```', "m")
    assert verdict.matches is True


def test_parse_verdict_defaults_a_missing_reason():
    verdict = parse_verdict('{"matches": true}', "m")
    assert verdict.reason == ""


def test_parse_verdict_truncates_a_rambling_reason():
    verdict = parse_verdict('{"matches": true, "reason": "' + "x" * 2000 + '"}', "m")
    assert len(verdict.reason) == 500


def test_parse_verdict_rejects_a_reply_with_no_json():
    with pytest.raises(ValueError, match="no JSON object"):
        parse_verdict("I cannot answer that.", "m")


def test_parse_verdict_rejects_json_without_a_verdict():
    # Defaulting a missing verdict either way would invent a decision.
    with pytest.raises(ValueError, match="missing 'matches'"):
        parse_verdict('{"reason": "not sure"}', "m")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("false", False), ("yes", True), ("no", False), ("TRUE", True)],
)
def test_parse_verdict_reads_quoted_booleans_correctly(raw, expected):
    # `bool("false")` is True in Python, so a quoted "false" would be recorded as a match unless
    # the string case is handled explicitly.
    verdict = parse_verdict('{"matches": "' + raw + '", "reason": "r"}', "m")
    assert verdict.matches is expected


@pytest.mark.parametrize("raw", ['"maybe"', "1", "null", "[]"])
def test_parse_verdict_rejects_an_unreadable_verdict(raw):
    # Guessing here would fabricate a decision. Raising leaves the row unjudged for a retry.
    with pytest.raises(ValueError):
        parse_verdict('{"matches": ' + raw + ', "reason": "r"}', "m")
