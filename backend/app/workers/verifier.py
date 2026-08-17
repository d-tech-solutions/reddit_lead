"""The precision gate: ask Claude whether a post really matches a watcher's intent.

The vector stage is tuned for recall — it hands over candidates that are topically close and
point the right way, and is wrong often enough that acting on it directly would spam users
(docs/PROGRESS.md, 2026-07-30: raw similarity put six offer posts above every request, at a
confident-looking 0.51–0.63). This stage decides yes or no, and its verdict is what reaches the
user.

Structured as a protocol plus one implementation, same as `embedding_source`: the worker depends
on the interface and the tests substitute a fake that never calls the network.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Claude Haiku-class, per ARCHITECTURE.md §5 — this runs on every candidate, so cost per call is
# the constraint. Worth re-testing against a larger model once there is labelled data to score on.
DEFAULT_MODEL = "claude-haiku-4-5"

# A verdict needs a word or two of reasoning, not an essay. Kept small because this is per
# candidate and the reason is only ever read by a human debugging a bad match.
MAX_TOKENS = 300

# Truncate post text before sending. Reddit posts run long and the decision is almost always
# clear from the opening; this bounds per-call cost.
MAX_POST_CHARS = 4000

SYSTEM_PROMPT = """\
You judge whether a Reddit post matches what a user is watching for. You will be given the \
user's description of what they want to find, the direction they care about, and one post.

Answer with JSON only: {"matches": true|false, "reason": "<one short sentence>"}.

Decide on three things, all of which must hold for a match:

1. Direction. If the user wants someone REQUESTING work, the poster must be looking to hire, \
buy, or get something done. If the user wants someone OFFERING, the poster must be advertising \
their own services or availability. This is the most common way a post looks relevant but is \
not: a post about the same topic from the opposite side of the transaction is NOT a match. Judge \
this from what the poster is actually doing, not from tags or title formatting, which posters \
often get wrong.

2. Subject. The post must be about the specific kind of work the user described. Same direction \
but a different field is not a match — someone hiring a marketer does not match a user watching \
for people hiring developers.

3. Substance. The post must be a real instance of the thing, not a discussion of it, a meta \
post, a survey, or a job board digest.

When the post is too vague to tell, answer false. A missed match costs the user one opportunity; \
a false match costs them trust in every future alert.\
"""


@dataclass
class Verdict:
    matches: bool
    reason: str
    model: str


class IntentVerifier(Protocol):
    async def verify(
        self, intent_text: str, direction: str, title: str, body: str
    ) -> Verdict: ...

    async def close(self) -> None: ...


# Assemble the single user turn describing one candidate. Kept as one block so the stable system
# prompt stays byte-identical across calls and the volatile part is all at the end.
def build_prompt(intent_text: str, direction: str, title: str, body: str) -> str:
    wanted = "OFFERING their services" if direction == "offering" else "REQUESTING work"
    post = f"{title}\n\n{body}".strip() if body.strip() else title.strip()
    return (
        f"The user wants to find posts from someone {wanted}.\n\n"
        f"What the user described: {intent_text}\n\n"
        f"--- POST ---\n{post[:MAX_POST_CHARS]}\n--- END POST ---"
    )


# Pull the verdict out of Claude's reply. Tolerates the model wrapping JSON in prose or a fence,
# because a parse failure here would otherwise discard a decision that was actually made.
def parse_verdict(text: str, model: str) -> Verdict:
    cleaned = text.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object in verifier reply: {cleaned[:200]!r}")

    payload = json.loads(cleaned[start : end + 1])
    if "matches" not in payload:
        raise ValueError(f"verifier reply missing 'matches': {payload!r}")

    return Verdict(
        matches=_coerce_bool(payload["matches"]),
        reason=str(payload.get("reason", "")).strip()[:500],
        model=model,
    )


# Read a verdict flag that may arrive as a real boolean or as a quoted string.
# `bool("false")` is True, so the string case has to be handled explicitly or a quoted "false"
# would be recorded as a match.
def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes"):
            return True
        if lowered in ("false", "no"):
            return False
        raise ValueError(f"verifier returned an unreadable 'matches' value: {value!r}")
    raise ValueError(f"verifier returned a non-boolean 'matches' value: {value!r}")


class ClaudeIntentVerifier:
    def __init__(self, api_key: str, model: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    # Ask Claude for one yes/no verdict on one candidate.
    # Raises on API failure so the caller leaves `llm_verified` NULL and the sweep retries.
    async def verify(self, intent_text: str, direction: str, title: str, body: str) -> Verdict:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": build_prompt(intent_text, direction, title, body),
                }
            ],
        )

        # A safety refusal is not a "no" — treat it as a failure so the row stays unjudged rather
        # than silently recording a rejection the model never actually made.
        if response.stop_reason == "refusal":
            raise RuntimeError(f"verifier refused to answer (model={self._model})")

        text = next((block.text for block in response.content if block.type == "text"), "")
        _log_usage(self._model, getattr(response, "usage", None))
        return parse_verdict(text, self._model)

    async def close(self) -> None:
        await self._client.close()


# Log tokens and estimated cost per verdict. This is the second stage that spends money per post,
# and unlike embedding it scales with K rather than with post count (ARCHITECTURE.md §7).
def _log_usage(model: str, usage: Any) -> None:
    if usage is None:
        return
    # Claude Haiku 4.5: $1 per million input tokens, $5 per million output.
    cost = (usage.input_tokens / 1_000_000) + (usage.output_tokens * 5 / 1_000_000)
    logger.info(
        "verify: model=%s in=%d out=%d est_cost_usd=%.6f",
        model,
        usage.input_tokens,
        usage.output_tokens,
        cost,
    )


# Construct the verifier, failing at startup with an actionable message when the key is missing
# rather than on the first candidate. Same contract as build_embedding_provider.
def build_verifier(api_key: str, model: str) -> IntentVerifier:
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is required to run the matcher. "
            "Set it in backend/.env for local runs, or in the root .env for docker compose."
        )
    return ClaudeIntentVerifier(api_key, model)
