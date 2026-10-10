# Ingestion worker

The ingestion worker ([backend/app/workers/ingest.py](../../../backend/app/workers/ingest.py))
is a standalone process — `python -m app.workers.ingest` — that runs a plain interval loop rather
than an Arq job, since it's the producer at the head of the pipeline, not a consumer.

## Startup

`main()` (ingest.py:99-136):

1. Loads settings and picks a post source based on `REDDIT_FETCH_MODE` — either `RssSource`
   (public `.rss` feeds, no credentials, dev-only, no post bodies) or `ApiSource` (official
   asyncpraw OAuth, read-only, needed for production). Both implement the same `PostSource`
   protocol so the worker doesn't care which one is active
   (reddit_source.py:22-25).
2. Connects to Redis (Arq). If that fails, it logs and keeps going with `redis = None` — a
   missing Redis shouldn't halt ingestion, since the matcher has its own backfill sweep to catch
   anything not enqueued.
3. Loops forever: run one poll cycle, sleep `REDDIT_POLL_INTERVAL_SECONDS`, repeat. On exit
   (e.g. Ctrl+C), it closes the source client and the Redis pool in a `finally` block.

## Each poll cycle

`poll_once()` (ingest.py:71-96):

1. `get_active_subreddits()` selects the distinct `unnest(subreddits)` of active watchers in SQL.
   If no watchers are active, the cycle ends immediately.
2. For each subreddit, it calls `source.fetch_window(subreddit, since, INGEST_MAX_POSTS_PER_POLL)`
   where `since` is now minus `NEW_WATCHER_LOOKBACK_MINUTES` (60) — posts from the last hour only,
   never "the latest N whenever they were made". A fetch failure for one subreddit is logged and
   skipped; it doesn't abort the whole cycle.
3. `store_posts()` drops anything older than the window (a post with no timestamp is stamped as
   just posted), inserts the ids into `seen_posts` (`ON CONFLICT DO NOTHING … RETURNING`), and
   queues only the genuinely new ones in `reddit_posts`. `seen_posts` outlives the queue row, which
   the matcher deletes once the post is judged, so a judged post is never re-ingested.
4. `enqueue_for_matching()` (ingest.py:54-68) hands each new post id to Arq as a `match_post`
   job. The job id is derived from the post id (`match_post:{post_id}`), so re-enqueuing the same
   post is a no-op. Enqueue failures are caught and logged per-post, never fatal.
5. Logs a per-subreddit summary (`fetched=N new=M`), then a cycle-level summary
   (`subreddits=N new_posts=M`), and returns the total new-post count.

## Fetch mode detail

From [backend/app/workers/reddit_source.py](../../../backend/app/workers/reddit_source.py):

- `RssSource` hits `https://www.reddit.com/r/{subreddit}/new/.rss`, parses it with
  `feedparser`, and maps each entry to the common dict shape. Reddit RSS ids look like
  `t3_abc123`; it strips the `t3_` prefix to match the API's bare id format. Body is always
  empty (RSS gives rendered HTML, not raw selftext).
- `ApiSource` wraps `asyncpraw.Reddit` in read-only mode and calls `sub.new(limit=limit)`,
  giving real `selftext` bodies and UTC timestamps.

## Net result

Each cycle queues new, previously-unseen, recent posts across every actively-watched subreddit as
rows in `reddit_posts` (the matcher's work queue), each with a `match_post` job already enqueued.
See [match.md](match.md) for what happens to them next.
