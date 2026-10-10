"""The verifier: ask an LLM whether a post matches each candidate watcher's intent.

One batched call handles every watcher currently subscribed to a post's subreddit — the model
sees all of them side by side and returns one verdict per candidate. This both bounds LLM spend
per post (one call per post, or a handful for a very busy subreddit, instead of one call per
candidate) and lets the model directly contrast similar-sounding intents instead of judging each
in isolation, which is what let a vector-based gate get direction backwards in the earlier design
(see docs/matcher/README.md).

Structured as a protocol plus one implementation, same shape the codebase already used for the
old embedding provider: the worker depends on the interface, and tests substitute a fake that
never calls the network.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

# Cheap and fast, run once per post (or per batch of candidates) rather than per candidate.
DEFAULT_MODEL = "gpt-4o-mini"

# Reasoning plus a verdict per candidate, times up to MATCH_BATCH_SIZE candidates in one reply.
MAX_OUTPUT_TOKENS = 2000

# Truncate post text before sending. Reddit posts run long and the decision is almost always
# clear from the opening; this bounds per-call cost.
MAX_POST_CHARS = 4000

# Truncate each watcher's intent so one unusually long description doesn't crowd out the others.
MAX_INTENT_CHARS = 1000

SYSTEM_PROMPT = """\
You judge whether a Reddit post matches what each of several users is watching for. You will be \
given one post and a numbered list of candidate watchers, each with their own description of \
what they want to find. Return one verdict per candidate, referenced by its number.

For each candidate, decide on three things, all of which must hold for a match:

1. Direction. Read the candidate's description and work out which side of a transaction they \
want: someone REQUESTING work (looking to hire, buy, or get something done), someone OFFERING \
work (advertising their own services or availability), or neither (they just want to know about \
posts on a topic, with no request or offer implied). Then check which side the poster in THIS \
POST is actually on. A post about the same topic from the opposite side of the transaction is \
NOT a match. Judge this from what the poster is actually doing, not from tags or title \
formatting, which posters often get wrong. If the candidate is watching for a topic with no \
particular side, direction does not rule the post out — judge on subject and substance alone.

2. Subject. The post must be about the specific kind of work or topic the candidate described. \
Same direction but a different field is not a match — someone hiring a marketer does not match a \
candidate watching for people hiring developers.

3. Substance. The post must be a real instance of the thing, not a discussion of it, a meta post, \
a survey, or a job board digest.

When a candidate's description is too vague to judge, or the post is too vague to tell, answer \
false for that candidate. A missed match costs the user one opportunity; a false match costs them \
trust in every future alert — ties go to false.

Give a one-sentence reasoning for every candidate, then your verdict, in the order they were \
given. Cover every candidate number exactly once.\
"""

# The reverse shape, used when a new watcher catches up on recent posts: one watcher, many posts.
POSTS_SYSTEM_PROMPT = """\
You judge which of several Reddit posts match what ONE user is watching for. You will be given \
the user's description of what they want to find and a numbered list of posts. Return one \
verdict per post, referenced by its number.

For each post, decide on three things, all of which must hold for a match:

1. Direction. Work out which side of a transaction the user wants: someone REQUESTING work \
(looking to hire, buy, or get something done), someone OFFERING work (advertising their own \
services or availability), or neither (they just want to know about posts on a topic). Then check \
which side the poster is actually on. A post about the same topic from the opposite side of the \
transaction is NOT a match. Judge this from what the poster is actually doing, not from tags or \
title formatting. If the user is watching for a topic with no particular side, direction does \
not rule the post out — judge on subject and substance alone.

2. Subject. The post must be about the specific kind of work or topic the user described. Same \
direction but a different field is not a match.

3. Substance. The post must be a real instance of the thing, not a discussion of it, a meta post, \
a survey, or a job board digest.

When the description is too vague to judge, or a post is too vague to tell, answer false for that \
post. A missed match costs the user one opportunity; a false match costs them trust in every \
future alert — ties go to false.

Give a one-sentence reasoning for every post, then your verdict, in the order they were given. \
Cover every post number exactly once.\
"""

VERDICT_SCHEMA: dict[str, Any] = {
    "name": "verdicts",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_number": {"type": "integer"},
                        "reasoning": {"type": "string"},
                        "matches": {"type": "boolean"},
                    },
                    "required": ["candidate_number", "reasoning", "matches"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["verdicts"],
        "additionalProperties": False,
    },
}


@dataclass
class Verdict:
    watcher_id: UUID
    matches: bool
    reason: str
    model: str


@dataclass
class PostVerdict:
    reddit_post_id: str
    matches: bool
    reason: str
    model: str


class IntentVerifier(Protocol):
    async def verify_batch(
        self, post_title: str, post_body: str, candidates: list[tuple[UUID, str]]
    ) -> list[Verdict]:
        """Return one verdict per candidate; raise on failure rather than guessing."""
        ...

    async def verify_posts(
        self, intent_text: str, posts: list[tuple[str, str, str]]
    ) -> list[PostVerdict]:
        """Judge posts, given as (reddit_post_id, title, body), against one watcher's intent.

        Raise on failure rather than guessing.
        """
        ...

    async def close(self) -> None: ...


def build_prompt(post_title: str, post_body: str, candidates: list[tuple[UUID, str]]) -> str:
    """Assemble the user turn: the post, then every candidate numbered so the model's reply maps
    back to a watcher_id in code rather than asking it to echo a UUID verbatim."""
    post = f"{post_title}\n\n{post_body}".strip() if post_body.strip() else post_title.strip()
    numbered = "\n\n".join(
        f"Candidate {index}: {intent_text[:MAX_INTENT_CHARS]}"
        for index, (_, intent_text) in enumerate(candidates, start=1)
    )
    return (
        f"--- POST ---\n{post[:MAX_POST_CHARS]}\n--- END POST ---\n\n"
        f"--- CANDIDATES ---\n{numbered}\n--- END CANDIDATES ---"
    )


def build_posts_prompt(intent_text: str, posts: list[tuple[str, str, str]]) -> str:
    """Assemble the user turn for a catch-up: the watcher's intent, then each post numbered."""
    blocks = []
    for index, (_, title, body) in enumerate(posts, start=1):
        text = f"{title}\n\n{body}".strip() if body.strip() else title.strip()
        blocks.append(f"Post {index}:\n{text[:MAX_POST_CHARS]}")
    return (
        f"--- WATCHER ---\n{intent_text[:MAX_INTENT_CHARS]}\n--- END WATCHER ---\n\n"
        f"--- POSTS ---\n" + "\n\n".join(blocks) + "\n--- END POSTS ---"
    )


def apply_post_numbers(
    raw_verdicts: list[dict[str, Any]], posts: list[tuple[str, str, str]], model: str
) -> list[PostVerdict]:
    """Map the model's numbered verdicts back to reddit post ids, dropping out-of-range numbers."""
    verdicts: list[PostVerdict] = []
    for entry in raw_verdicts:
        number = entry.get("candidate_number")
        if not isinstance(number, int) or not (1 <= number <= len(posts)):
            logger.warning("verify_posts: model returned an out-of-range number=%r", number)
            continue
        verdicts.append(
            PostVerdict(
                reddit_post_id=posts[number - 1][0],
                matches=bool(entry.get("matches", False)),
                reason=str(entry.get("reasoning", "")).strip()[:500],
                model=model,
            )
        )
    return verdicts


def apply_candidate_numbers(
    raw_verdicts: list[dict[str, Any]], candidates: list[tuple[UUID, str]], model: str
) -> list[Verdict]:
    """Turn the model's numbered verdicts back into Verdict rows keyed by watcher_id.

    A candidate number outside the batch, or one the model skipped entirely, is logged and left
    out — the caller's match row for that candidate stays NULL for the backfill sweep to retry,
    rather than guessing at a verdict the model never actually gave.
    """
    verdicts: list[Verdict] = []
    for entry in raw_verdicts:
        number = entry.get("candidate_number")
        if not isinstance(number, int) or not (1 <= number <= len(candidates)):
            logger.warning(
                "verify_batch: model returned an out-of-range candidate_number=%r", number
            )
            continue
        watcher_id, _ = candidates[number - 1]
        verdicts.append(
            Verdict(
                watcher_id=watcher_id,
                matches=bool(entry.get("matches", False)),
                reason=str(entry.get("reasoning", "")).strip()[:500],
                model=model,
            )
        )
    return verdicts


class OpenAIIntentVerifier:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def verify_batch(
        self, post_title: str, post_body: str, candidates: list[tuple[UUID, str]]
    ) -> list[Verdict]:
        """Ask the model for one verdict per candidate watcher against one post.

        Raises on API failure or a refusal so the caller leaves those match rows NULL and the
        sweep retries them.
        """
        if not candidates:
            return []

        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(post_title, post_body, candidates)},
            ],
            response_format={"type": "json_schema", "json_schema": VERDICT_SCHEMA},
        )

        message = response.choices[0].message

        # A refusal is not a "no" for every candidate — treat it as a failure so the rows stay
        # unjudged rather than silently recording rejections the model never actually made.
        refusal = getattr(message, "refusal", None)
        if refusal:
            raise RuntimeError(f"verifier refused to answer (model={self._model}): {refusal}")

        payload = json.loads(message.content or "{}")
        raw_verdicts = payload.get("verdicts", [])
        _log_usage(self._model, getattr(response, "usage", None))
        return apply_candidate_numbers(raw_verdicts, candidates, self._model)

    async def verify_posts(
        self, intent_text: str, posts: list[tuple[str, str, str]]
    ) -> list[PostVerdict]:
        """Ask the model for one verdict per post against a single watcher's intent."""
        if not posts:
            return []

        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": POSTS_SYSTEM_PROMPT},
                {"role": "user", "content": build_posts_prompt(intent_text, posts)},
            ],
            response_format={"type": "json_schema", "json_schema": VERDICT_SCHEMA},
        )
        message = response.choices[0].message
        refusal = getattr(message, "refusal", None)
        if refusal:
            raise RuntimeError(f"verifier refused to answer (model={self._model}): {refusal}")

        payload = json.loads(message.content or "{}")
        _log_usage(self._model, getattr(response, "usage", None))
        return apply_post_numbers(payload.get("verdicts", []), posts, self._model)

    async def close(self) -> None:
        await self._client.close()


def _log_usage(model: str, usage: Any) -> None:
    """Log tokens and estimated cost per batch call.

    GPT-4o-mini: $0.15 per million input tokens, $0.60 per million output — update these if the
    model or its published rate changes.
    """
    if usage is None:
        return
    cost = (usage.prompt_tokens * 0.15 + usage.completion_tokens * 0.60) / 1_000_000
    logger.info(
        "verify_batch: model=%s in=%d out=%d est_cost_usd=%.6f",
        model,
        usage.prompt_tokens,
        usage.completion_tokens,
        cost,
    )


def build_verifier(api_key: str, model: str) -> IntentVerifier:
    """Construct the verifier, failing fast with an actionable message when the key is missing
    rather than on the first batch."""
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is required to run the matcher. "
            "Set it in backend/.env for local runs, or in the root .env for docker compose."
        )
    return OpenAIIntentVerifier(api_key, model)
