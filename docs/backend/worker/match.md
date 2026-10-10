# Matcher worker

The matcher ([backend/app/workers/match.py](../../../backend/app/workers/match.py)) runs as an
Arq consumer (`arq app.workers.match.WorkerSettings`), not an interval loop. It is triggered by the
ingestion worker the moment a post is queued, with a backfill cron sweep as the safety net, and it
also runs the new-watcher catch-up job and the retention cron.

## Where posts live

| Table | Role | Lifetime |
|---|---|---|
| `reddit_posts` | **Work queue.** A row exists only until the LLM has judged the post. | Deleted when judged. |
| `matched_posts` | Full content of posts at least one watcher confirmed. | Until no match references it (see Retention). |
| `matches` | One row per confirmed (watcher, matched post): reason, model, `notified_at`, `read_at`. | Until the owner is inactive 90 days. |
| `seen_posts` | Dedup memory: just the Reddit id and `seen_at`. | `SEEN_POSTS_RETENTION_DAYS` (7). |
| `match_stats` | Daily `reviewed` / `confirmed` counters per (watcher, subreddit). Feeds analytics. | Kept. |
| `rejection_log` | Truncated sample of rejections (title, permalink, reason). No FK to posts. | `REJECTION_LOG_RETENTION_DAYS` (7). |

Rejected candidates are **not** stored as `matches` rows. They are counted in `match_stats` and
sampled into `rejection_log`, so `matches` only grows with real hits.

## The `match_post` job

1. **Claim** (`claim_post`): `SELECT … FOR UPDATE SKIP LOCKED` on the queue row, then set
   `locked_until = now + MATCH_CLAIM_SECONDS` and `attempts += 1`. Several workers can run without
   taking the same post; a post already settled or held by another worker returns 0.
2. **Candidates** (`fetch_candidate_watchers`): active watchers with
   `subreddits @> ARRAY[subreddit]` (served by the GIN index `ix_watchers_subreddits_gin`) **and**
   `watchers.created_at <= post.posted_at`. The second condition is the new-watcher rule below.
   No candidates: the post is deleted without calling the LLM.
3. **Verify**: candidates are chunked by `MATCH_BATCH_SIZE`, one `verify_batch` call per chunk. No
   DB transaction is open during these network calls.
4. **Settle** (`process_post`), in **one transaction**: `store_outcomes` (see
   [outcomes.py](../../../backend/app/workers/outcomes.py)) upserts the post into `matched_posts`
   and inserts `matches` for confirmations, samples rejections into `rejection_log`, bumps
   `match_stats`; then the queue row is deleted. A crash cannot lose a match or leave a post
   half-moved. After the commit, new match ids are enqueued for the notify worker.
5. **Failure**: if any chunk fails (or the model skips a candidate) the post stays queued with a
   backoff (`RETRY_BACKOFF_SECONDS × attempts`). At `MATCH_MAX_ATTEMPTS` it is settled with the
   verdicts it has, or dropped if it has none (logged at ERROR). `purge_exhausted` also drops posts
   whose worker died repeatedly.

## The backfill cron job

`backfill()` runs at startup and every `MATCH_BACKFILL_INTERVAL_MINUTES`. It drops exhausted posts,
then claims the oldest claimable posts older than `MATCH_BACKFILL_MIN_AGE_SECONDS` (so it doesn't
race the job enqueued at ingest) and settles each. A post that nobody watches is simply deleted,
so the sweep never re-checks the same post.

## New watchers: the one-hour rule

A watcher only judges posts made **at or after its `created_at`**. The hour before that is covered
by a separate job so the two never judge the same post:

- `catchup_watcher(watcher_id, subreddits, until)` is enqueued by the API on watcher create (and,
  for just the added subreddits, on a PATCH that adds some). It fetches
  `[until − NEW_WATCHER_LOOKBACK_MINUTES, until)` straight from Reddit via
  `source.fetch_window` (the posts were already deleted from the queue if nobody matched them),
  caps at `CATCHUP_MAX_POSTS` per subreddit, and judges them against that one watcher in batches of
  `CATCHUP_BATCH_SIZE` using `verifier.verify_posts`. Results go through the same `store_outcomes`.
- Ingestion also never stores a post older than `NEW_WATCHER_LOOKBACK_MINUTES`, so a freshly polled
  subreddit no longer hands a new watcher the latest N posts regardless of age.
- The enqueue is best-effort ([services/queue.py](../../../backend/app/services/queue.py)): a Redis
  outage never fails watcher creation, it only skips the catch-up.

## Retention cron

`retention()` runs hourly (`services/retention.py`, batched deletes so no long locks):
`seen_posts` and `rejection_log` past their windows; `matches` of users whose
`users.last_active_at` is older than `USER_INACTIVITY_RETENTION_DAYS` (90); then `matched_posts`
that no match references. `last_active_at` is refreshed by `get_current_user` at most once per
`LAST_ACTIVE_TOUCH_MINUTES`.

## Worker config

- `functions = [match_post, catchup_watcher]`; `cron_jobs = [backfill, retention]`.
- `startup()` builds the `IntentVerifier` and the Reddit `PostSource` once per process (the source
  is used by the catch-up job); `shutdown()` closes both.
- `queue_name = MATCH_QUEUE` (`"arq:match"`). Any new `enqueue_job` call must pass `_queue_name`.
- `max_tries = 3` per Arq job; beyond that the backfill sweep takes over.

See [verifier.md](verifier.md) for how the LLM calls work and [ingest.md](ingest.md) for how posts
reach the queue.
