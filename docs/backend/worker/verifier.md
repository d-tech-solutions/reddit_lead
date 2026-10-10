# The verifier

The verifier ([backend/app/workers/verifier.py](../../../backend/app/workers/verifier.py)) is the
LLM call the [matcher](match.md) makes to decide whether a post actually matches each candidate
watcher's intent. It's a protocol plus one implementation — `IntentVerifier` — the same shape the
codebase used for an earlier embedding-based provider, so the worker depends on the interface and
tests can substitute a fake that never calls the network.

## Why one batched call per post

One call handles every watcher currently subscribed to a post's subreddit — the model sees all
candidates side by side and returns one verdict per candidate in a single response. This:

- Bounds LLM spend per post to one call (or a handful, if `MATCH_BATCH_SIZE` splits a busy
  subreddit into chunks) instead of one call per candidate.
- Lets the model directly contrast similar-sounding intents rather than judging each in
  isolation — judging in isolation is what let an earlier vector-based gate get direction
  backwards (a post offering a service scoring as a match for someone wanting to hire).

## The judging criteria

`SYSTEM_PROMPT` (verifier.py:38-67) instructs the model to require all three of the following for
a match, per candidate:

1. **Direction** — is the candidate watching for someone *requesting* work, someone *offering*
   work, or neither? The post's poster must be on the matching side of that same transaction.
   Judged from what the poster is actually doing, not from tags or title formatting (which
   posters often get wrong).
2. **Subject** — the post must be about the specific kind of work/topic described, not just the
   same direction in a different field.
3. **Substance** — the post must be a real instance of the thing, not a discussion, meta post,
   survey, or job-board digest.

Ties go to false: a vague candidate description or a vague post is judged as no match. The prompt
frames this explicitly — a missed match costs one opportunity, a false match costs trust in every
future alert.

## Request/response shape

- `build_prompt()` (verifier.py:113-124) assembles the user turn: the post (title + body,
  truncated to `MAX_POST_CHARS` = 4000 chars) followed by a numbered list of candidates (each
  intent truncated to `MAX_INTENT_CHARS` = 1000 chars). Candidates are numbered rather than keyed
  by UUID so the model doesn't have to echo a UUID verbatim — `apply_candidate_numbers()` maps the
  numbers back to `watcher_id`s in code.
- The call uses a strict JSON schema (`VERDICT_SCHEMA`, verifier.py:69-92) via
  `response_format={"type": "json_schema", ...}`, requiring `candidate_number`, `reasoning`, and
  `matches` for every entry.
- `apply_candidate_numbers()` (verifier.py:127-153) turns the raw response into `Verdict` objects.
  A candidate number that's out of range or missing from the reply is logged and dropped — its
  match row stays NULL for the backfill sweep to retry, rather than guessing at a verdict the
  model never gave.
- A model **refusal** is treated as a failure, not a blanket "no" — `OpenAIIntentVerifier.verify_batch()`
  (verifier.py:163-195) raises `RuntimeError` if `message.refusal` is set, so the caller leaves
  those rows unjudged instead of recording rejections the model never actually made.

## Implementation

`OpenAIIntentVerifier` (verifier.py:156-198) wraps `AsyncOpenAI`, defaulting to `gpt-4o-mini`
(`DEFAULT_MODEL`, verifier.py:26) — cheap and fast, run once per batch rather than per candidate.
`max_tokens=2000` (`MAX_OUTPUT_TOKENS`) covers a one-sentence reasoning plus a verdict for up to
`MATCH_BATCH_SIZE` candidates in one reply.

`_log_usage()` (verifier.py:201-216) logs prompt/completion tokens and an estimated cost per call,
using gpt-4o-mini's published rate ($0.15/M input, $0.60/M output) — update the constants there if
the model or its pricing changes.

`build_verifier()` (verifier.py:219-227) fails fast with an actionable error if `OPENAI_API_KEY`
is missing, rather than failing on the first batch call.
