# Match feed

Code-level walkthrough of the feed — the surface that finally shows users what the pipeline found.
Companion to `docs/matcher/` (which writes the rows this reads) and `docs/watcher-ui/` (the other
frontend surface).

**What it does, in one sentence**: shows a signed-in user the confirmed matches their watchers
caught, newest first, and tracks which ones they have opened.

## 1. Files involved

| File | Purpose |
|---|---|
| [`backend/app/schemas/match.py`](../../backend/app/schemas/match.py) | Response shapes. Post and watcher are embedded in each item. |
| [`backend/app/services/matches.py`](../../backend/app/services/matches.py) | Feed query, cursor encoding, unread count, read stamping. |
| [`backend/app/api/v1/endpoints/matches.py`](../../backend/app/api/v1/endpoints/matches.py) | `GET /matches`, `POST /matches/{id}/read`, `POST /matches/read-all`. |
| [`backend/alembic/versions/e5b2d84a9c17_add_match_feed_index.py`](../../backend/alembic/versions/e5b2d84a9c17_add_match_feed_index.py) | Two partial indexes: the feed and the unread count. |
| [`backend/scripts/seed_matches.py`](../../backend/scripts/seed_matches.py) | Dev-only. Writes fake confirmed matches so the UI works without live API keys. |
| [`frontend/src/app/matches/page.tsx`](../../frontend/src/app/matches/page.tsx) | Server Component: loads the first page, picks an empty state. |
| [`frontend/src/components/match-feed.tsx`](../../frontend/src/components/match-feed.tsx) | Client Component: paging, mark-read, mark-all-read. |
| [`frontend/src/components/match-card.tsx`](../../frontend/src/components/match-card.tsx) | Client Component: one match. |
| [`frontend/src/app/actions/matches.ts`](../../frontend/src/app/actions/matches.ts) | Server Actions for all three calls. |

## 2. Only confirmed matches are product

`matches` holds a row for **every candidate the vector gate produced**, which is deliberate — those
rows are the labelled data that will eventually calibrate the gate (see `docs/PROGRESS.md`, open
decisions). The feed filters to `llm_verified IS TRUE`.

The column is three-valued and the filter is written `.is_(True)`, not a truthiness test:

| Value | Means | In the feed? |
|---|---|---|
| `NULL` | The verifier has not run yet | **No** |
| `False` | The verifier ran and said no | **No** |
| `True` | Confirmed | Yes |

`NULL` has to be excluded as firmly as `False`. A pending candidate is not a weak match, it is an
unknown one, and showing it would put the vector gate's raw output — which the whole verifier stage
exists to filter — in front of users.

## 3. Ownership is a join, every time

`matches` has no `user_id` column. The only link to a user is `matches → watchers.user_id`, so
every query in `services/matches.py` joins through `watchers` and filters on it. Dropping that join
does not fail loudly; it just returns everyone's feed.

The `?watcher_id=` filter **narrows** an already user-scoped query rather than replacing the scope.
Written the other way round it would be a way to read any user's matches by guessing an id, which
is what `test_watcher_filter_cannot_reach_another_users_watcher` pins down.

`POST /matches/{id}/read` answers **404** for a match the caller does not own, not 403 — the same
reasoning as the watcher endpoints, since a 403 confirms the id exists.

## 4. Sorted by when we matched it, not when it was posted

`reddit_posts.posted_at` is nullable — the RSS fetch mode does not always supply a timestamp — so
it cannot be a sort key without a `COALESCE` that would make the index unusable. The feed sorts on
`matches.created_at`, which is always present and is also the order the user experiences: matches
appear when we find them.

The post's own date is still displayed.

## 5. Cursor paging, not OFFSET

New matches arrive at the head of this feed continuously. With `LIMIT/OFFSET`, a row inserted
between two page reads shifts the window by one, and the user sees an item twice or misses it
entirely. The cursor compares against the last row's sort key instead, so a page boundary means the
same thing regardless of what arrived since.

```
WHERE (created_at, id) < (:cursor_created_at, :cursor_id)
ORDER BY created_at DESC, id DESC
```

**The `id` in the key is load-bearing.** Postgres' `now()` is transaction start time, and the
matcher writes a whole batch of candidates in one transaction — so sibling rows genuinely share a
`created_at` to the microsecond. Paging on the timestamp alone would silently drop whichever
siblings fell after the boundary. Two tests cover this:
`test_matches_sharing_a_timestamp_all_appear` and `test_a_new_match_does_not_shift_the_next_page`.

The cursor is base64 over `"{iso timestamp}|{uuid}"`. That is not a security measure — it is
trivially reversible — it just discourages clients from constructing cursors by hand and then
breaking when the sort key changes. Anything unparseable is a **400**, not a 500.

## 6. What the API does not return

`similarity`, `direction_score` and `adjusted_score` are omitted from `MatchRead`.

They exist to calibrate the gate and mean nothing to a user. Exposed, a cosine similarity of 0.62
reads as "62% confident", which it is not — the number's useful range is roughly 0.5–0.65 and its
absolute value says very little. They stay queryable in the database, which is where the
calibration work happens anyway.

`llm_reason` **is** returned. A match that states why it matched is checkable, and a wrong one is
reportable — which is what makes the eventual feedback loop possible.

## 7. Indexes

```sql
CREATE INDEX ix_matches_feed ON matches (watcher_id, created_at DESC, id DESC)
  WHERE llm_verified IS TRUE;
CREATE INDEX ix_matches_unread ON matches (watcher_id)
  WHERE llm_verified IS TRUE AND read_at IS NULL;
```

The three pre-existing indexes are single-column and none serves this query: `ix_matches_watcher_id`
finds the rows but leaves a sort, and `ix_matches_llm_verified` is barely selective on a boolean.

Both are **partial** because rejected and unverified candidates are the bulk of the table — the
matcher writes one row per candidate and only a minority are confirmed. Keeping them out keeps the
indexes small.

## 8. Frontend: state lives in the client, not the route

`refresh()` is the post-mutation tool used everywhere in `docs/watcher-ui/`, but the feed
deliberately does **not** call it. The feed accumulates pages in client state, and re-rendering the
route would throw away everything the user had paged in — they would open one match and lose three
pages of scrollback.

So `MatchFeed` owns `items`, `cursor` and `unread`, and mutations update them locally. Other routes
stay correct because dynamic pages have a **zero client-cache stale time** since Next 15 (see
`staleTimes` in the Next docs), so navigating to `/dashboard` re-reads `/me` and gets a fresh badge.

**Reads go through a Server Action too.** `loadMoreMatchesAction` is a POST doing a GET's job, which
is unusual — the reason is that the Clerk token must stay server-side, the same rule as every other
call in this app. The alternative (a browser `fetch` to FastAPI) would mean shipping the token to
the client and turning CORS back on.

Every action re-checks auth, because Server Functions are reachable by direct POST.

## 9. Three empty states, not one

A single "no matches yet" message is wrong here, because the pipeline takes minutes to reach a new
watcher and the user cannot tell "still warming up" from "broken":

| Condition | Message |
|---|---|
| No watchers | "No watchers yet" + a link to create one |
| All watchers paused | "All your watchers are paused" |
| Watchers active, none embedded yet | "Still getting ready" |
| Watchers active and embedded | "Watching now — nothing has matched yet" |

The last one is the *correct* state and the one most likely to be misread as failure, which is why
it names how many watchers are running.

## 10. Seeding, and why it exists

A real match needs ingestion, an `OPENAI_API_KEY` for the embedding worker, and an
`ANTHROPIC_API_KEY` for the verifier. None of that was in place when this was built, so
`scripts/seed_matches.py` writes the end state directly:

```
docker compose exec api python -m scripts.seed_matches --email you@example.com
docker compose exec api python -m scripts.seed_matches --clear
```

It refuses to run unless `ENVIRONMENT` is local/development/test, and every row it writes carries a
`seed_` prefix on `reddit_post_id` so `--clear` finds its own rows and only its own rows. It is
mounted into the api container by docker-compose rather than baked into the image, so it cannot
ship to production.

## 11. Known gaps

- **No realtime.** The feed does not update while open; it fills in on reload. Fine at this cadence
  (matches arrive minutes apart at best), and the notification worker is the real answer.
- **No filtering UI.** The API takes `?watcher_id=`; nothing in the UI sets it.
- **No feedback control.** There is nowhere to say "this was a bad match", which is the input the
  gate calibration eventually needs.
- **`read_at` is set on click-through only** — a match read in the feed without opening the Reddit
  link stays unread.
- **No frontend tests.** Still no test framework in `/frontend`; flagged since the scaffold.
- **`notified_at` is still written by nothing.** That is the notification worker's column.
