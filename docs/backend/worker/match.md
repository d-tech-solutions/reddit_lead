# Matcher worker

The matcher ([backend/app/workers/match.py](../../../backend/app/workers/match.py)) runs as an
Arq consumer (`arq app.workers.match.WorkerSettings`), not an interval loop — it's triggered by
the ingestion worker the moment a post is inserted, with a backfill cron sweep as the safety net.
Same two-trigger shape as the rest of the pipeline (see [ingest.md](ingest.md)).

One stage per post: find every active watcher whose subreddit list covers this post (a plain DB
query, no vector search), then ask the verifier for one verdict per watcher in a single batched
call (chunked if there are many candidates). Every candidate is written to `matches` whether it
passes or fails, so the rejected rows stay a record of what the verifier saw and decided.

## The `match_post` job

`match_post()` (match.py:145-169), enqueued by the ingestion worker per new post id:

1. Loads the `RedditPost` by id. If it's gone (shouldn't normally happen), logs and returns 0.
2. `fetch_candidate_watchers()` (match.py:36-47) selects active `Watcher` rows whose
   `subreddits` array contains the post's subreddit — filtering in SQL keeps the candidate set
   small before anything reaches the LLM. No candidates means no work.
3. `store_placeholder_matches()` (match.py:55-76) bulk-inserts one row per (watcher, post) pair
   into `matches` with `llm_verified` left NULL, using `ON CONFLICT DO NOTHING` on the
   `uq_matches_pair` constraint so a retried job doesn't duplicate rows. These placeholders are
   what the backfill sweep looks for if a job dies mid-batch.
4. `chunk_watchers()` (match.py:50-52) splits the candidate list into groups of
   `MATCH_BATCH_SIZE` so one unusually busy subreddit doesn't produce one oversized LLM call.
5. For each chunk, `_verify_and_apply()` (match.py:112-142) calls
   `verifier.verify_batch(post.title, post.body, candidates)` and writes the results via
   `apply_verdicts()`. A failed chunk (API error, refusal, etc.) is logged and left NULL rather
   than failing the whole post — the backfill sweep retries it.
6. Returns the number of confirmed (matched) verdicts for that post.

`apply_verdicts()` (match.py:79-109) writes each verdict onto its placeholder row — `llm_verified`,
`llm_reason`, `llm_model`, `verified_at` — skipping any row that's missing or already judged, so a
retried batch is idempotent. One commit per batch.

## The backfill cron job

`backfill()` (match.py:203-239) runs on an Arq cron schedule (`run_at_startup=True`, then every
`MATCH_BACKFILL_INTERVAL_MINUTES`, converted to Arq's minute-set format by
`backfill_minutes()` at match.py:242-247). It catches two failure modes:

1. **Unjudged candidates** — `fetch_unverified_by_post()` (match.py:172-183) loads placeholder
   rows still stuck at `llm_verified IS NULL`, oldest first, grouped by post so each post gets
   one batched re-verification instead of one call per row.
2. **Posts nothing ever ran for** — `fetch_unmatched_posts()` (match.py:186-200) finds
   `RedditPost` rows with no `matches` row at all (an enqueue failure, or a job that exhausted
   its retries). It re-derives candidates and stores fresh placeholders for them. A post in a
   subreddit nobody watches keeps getting re-checked every sweep — cheap, and correct, since a
   watcher added later should still pick up an older post.

## Worker config

`WorkerSettings` (match.py:278-292):

- `functions = [match_post]` — the one Arq-triggered job.
- `cron_jobs` — the `backfill` sweep.
- `on_startup`/`on_shutdown` — `startup()` (match.py:250-265) builds the `IntentVerifier` once
  per worker process (not per job) and stores it in `ctx`; `shutdown()` (match.py:268-272) closes
  its HTTP client.
- `max_tries = 3` — three attempts per job, then it's left for the backfill sweep rather than
  retried indefinitely.

See [verifier.md](verifier.md) for how the LLM call itself works.
