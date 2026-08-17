# Progress

Living status tracker for the project. Update this as work happens — it's the source of truth for
"where are we" across sessions.

## Current phase: Planning (Phase 0)

| Doc | Status |
|---|---|
| [[PRD]] | Draft v1 complete |
| [[FEATURES]] | Draft v1 complete |
| [[ARCHITECTURE]] | Draft v1 complete |
| [[WORKFLOW]] | Draft v1 complete |
| PROGRESS (this doc) | Living |

## Decisions locked in (2026-07-25 brainstorm)

- Multi-user SaaS product (not a personal tool or open-source self-host project)
- Freemium monetization
- Watchers are scoped to user-picked subreddit(s) + a plain-language intent description (no
  auto-discovery of subreddits in MVP)
- MVP notification channels: Email + Telegram
- In-app dashboard/inbox is part of MVP (not notification-only)
- Feedback loop (thumbs up/down on matches) is roadmap, Phase 2 — not MVP
- All tiers get the same matching speed; tiers differ on watcher count, subreddit pool, and
  notification channels
- Two-stage matching (vector similarity retrieval + LLM intent verification) to solve the
  needs-vs-offers false positive problem
- Stack: FastAPI (`/backend`) + Next.js (`/frontend`), Postgres+pgvector, Redis, Docker/
  docker-compose for MVP scale (no Kubernetes yet)
- Product name: **PostPing**
- Auth provider: **Clerk**
- Email provider: **Resend**
- Task queue: **Arq**
- Tier limits (see [[PRD]] §6 for the full table):
  - Free: 1 watcher, 3 subreddits total
  - Standard: 3 watchers, 10 subreddits total
  - Premium: 10 watchers, 50 subreddits total
  - Enterprise: custom, contact sales
- Matcher gate approach: recall-favoring threshold or top-K per post (not a precisely-tuned
  cutoff) feeding the LLM verifier, calibrated later from logged real-traffic data rather than
  fixed at planning time — see [[ARCHITECTURE]] Matcher section for the full reasoning.

## Open decisions (not yet locked)

- [ ] Standard and Premium tier dollar pricing (amounts TBD)
- [ ] Whether Reddit will approve official API access at all (see 2026-07-26 ingestion log entry) —
      if declined, the product's data source needs rethinking, since RSS is not a viable
      production foundation
- [ ] Exact initial value for the matcher's similarity gate/K — **still open, but now instrumented**:
      `MATCH_TOP_K` ships at a deliberately loose 10 and every candidate's similarity, direction
      score, and verdict is logged to `matches`. Calibrate from that, not by guessing. See the
      2026-07-30 matcher entry.
- [ ] Whether a similarity **floor** is needed alongside top-K. Without one, every post in a watched
      subreddit costs at least one LLM call — spend scales as `posts × min(matching watchers, K)`.
      Deliberately not invented yet; the logged data is what should set it.
- [ ] Whether `claude-haiku-4-5` is the right verifier model. It follows [[ARCHITECTURE]] §5, but no
      measurement supports it over a larger model yet.
- [ ] Whether the subreddit pool counts the **sum** of watchers' lists or the **distinct union**.
      [[PRD]] §6's own 3/3/4 example implies sum, and that is what ships — but the ingestion worker
      polls the distinct union, so two watchers sharing a subreddit cost one poll while consuming
      two units of quota. Sum is the stricter reading; loosening later is easy, tightening on
      existing users is not.

## Milestones

- [x] Brainstorm core idea, tech stack direction
- [x] Lock product-shape decisions (audience, monetization, watcher scoping, notification
      channels, dashboard, feedback loop timing, tier differentiation)
- [x] Write PRD, Features, Architecture, Workflow docs
- [ ] Resolve open decisions above
- [x] Scaffold `/backend` (FastAPI project structure, Docker)
- [x] Scaffold `/frontend` (Next.js project structure, Docker)
- [x] `docker-compose.yml` for local dev (api, postgres+pgvector, redis, frontend) — worker
      services deferred until worker code exists
- [ ] Reddit API app registration + credentials — **blocked on Reddit approval**, see log below
- [x] Ingestion worker MVP (poll → dedupe → store) — queue hand-off now wired, see embedding worker
- [x] Embedding worker MVP (queue-driven + backfill sweep, pgvector columns) — pending one live
      end-to-end run with a real `OPENAI_API_KEY`, see log below
- [x] Matcher + LLM verifier MVP (top-K vector gate + direction axis + Claude verifier) — pending
      one live end-to-end run with a real `ANTHROPIC_API_KEY`, see log below
- [ ] Notification worker MVP (email + Telegram)
- [x] Watcher CRUD API (backend)
- [x] Watcher management UI (create, pause/resume, delete, plan usage) — editing still missing
- [x] Auth wired backend-side (Clerk token verification, `users` table, `watchers.user_id`) —
      frontend still calls nothing; Clerk webhook not built, see log
- [x] Match feed API + UI (paged, unread tracking) — see the 2026-07-31 log entry
- [x] Auth wired end-to-end (frontend → API) — code complete; the signed-in round trip still needs
      a human browser sign-in to confirm, see the 2026-07-30 UI entry
- [ ] Clerk `user.deleted` webhook — **cost leak until built**, see the 2026-07-30 auth entry
- [ ] Billing (Stripe) integration
- [ ] Monitoring stack wired (Sentry, Prometheus/Grafana, heartbeat check)
- [ ] First real end-to-end match, notified to a real user

## Log

- **2026-07-25**: Initial planning session. Discussed core concept, tech stack direction, and
  monitoring approach. Ran through product-shape decisions via structured Q&A (see "Decisions
  locked in" above). Wrote initial doc set (PRD, Features, Architecture, Workflow, Progress).
- **2026-07-25**: Scaffolded `/backend` — FastAPI app skeleton (`app/main.py`, versioned
  `api/v1` router, `/health` + `/api/v1/health`), pydantic-settings config, async SQLAlchemy
  DB session wiring (no models yet), Alembic initialized (async, empty `versions/`), pytest
  scaffold (health-check tests passing), and a multi-stage Dockerfile. Dependency manager:
  **uv** (confirmed via user Q&A). `uv` itself isn't installed on this machine, so
  `pyproject.toml`/`uv.lock` setup was hand-authored and smoke-tested with a throwaway pip venv
  instead of `uv sync`/`uv run`; Docker build was not executed locally.
- **2026-07-25**: Scaffolded `/frontend` — Next.js 16 (App Router) via `create-next-app`,
  TypeScript, Tailwind CSS v4, shadcn/ui (confirmed via user Q&A: **npm** package manager,
  **Tailwind + shadcn/ui**). Clerk wired end-to-end: `<ClerkProvider>` in the root layout,
  sign-in/sign-up routes, and a protected `/dashboard` placeholder using `auth()` +
  `redirectToSignIn()`. Note: Next.js 16 renamed `middleware.ts` to `proxy.ts` and deprecated
  Clerk's `createRouteMatcher`, so route protection is done per-page rather than in a middleware
  matcher — see `frontend/README.md` Notes section. Added a thin `lib/api.ts` stub pointed at the
  backend's `/api/v1` prefix (no real calls yet), `next.config.ts` `output: "standalone"`, and a
  multi-stage Dockerfile mirroring the backend's builder/runtime split. Verified: `npm run lint`
  and `npm run build` pass clean; dev server boots and `/dashboard` correctly redirects
  unauthenticated requests to `/sign-in`. No test framework wired yet (flagged as an open
  follow-up, not assumed). `npm audit` flags 12-15 high-severity issues, all transitive
  dev-tooling/Next-internal deps (eslint's minimatch chain, Next's bundled postcss/sharp) — not
  fixed via `--force` since that would downgrade Next to a very old major version; worth
  rechecking once real deps are added.
- **2026-07-26**: Added root `docker-compose.yml` (services: `postgres` on `pgvector/pgvector:pg16`
  with `docker/postgres/init.sql` running `CREATE EXTENSION vector` on first boot, `redis:7-alpine`,
  `api`, `frontend`) plus root `.env.example` for Postgres credential overrides. `worker-ingest`/
  `worker-embed`/`worker-match`/`worker-notify` from the architecture doc's compose topology are
  deferred — no worker entrypoints exist yet, so those services would just crash-loop; add them
  alongside the ingestion/embedding/matcher/notifier milestones. In the process, discovered
  `backend/uv.lock` was never generated (the 2026-07-25 backend scaffold session didn't have `uv`
  installed) — installed `uv` and ran `uv lock` to generate it, since the backend Dockerfile's
  `COPY pyproject.toml uv.lock` step hard-requires it. Verified the full stack with a real
  `docker compose up --build`: postgres/redis/api all report healthy, api's `/health` and
  `/api/v1/health` both return `{"status":"ok"}`, and frontend serves `/` with Clerk's dev-browser
  headers present. Stack was torn down (`docker compose down`) after verification.
- **2026-07-26**: Built the **ingestion worker** (`backend/app/workers/`). Added `watchers` and
  `reddit_posts` tables (Alembic migration `a2c4d2d568f4`) — `watchers` deliberately has no
  `user_id` yet, that arrives with the auth milestone when a `users` table exists to reference.
  Worker runs as its own process (`python -m app.workers.ingest`, service `worker-ingest` in
  compose), loops on `REDDIT_POLL_INTERVAL_SECONDS`, queries the distinct subreddits across active
  watchers, fetches recent posts, and inserts with `ON CONFLICT DO NOTHING` on the unique
  `reddit_post_id` — dedupe is enforced at the DB constraint, so it's race-safe across replicas.
  A fetch failure for one subreddit is logged and skipped rather than killing the cycle.

  **Reddit API access is now gated.** Reddit's [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)
  (late 2025) closed self-service app registration — access now requires submitting a request with
  a use-case description and waiting for manual approval, and requests are frequently declined.
  Because of this the worker has **two interchangeable fetch modes** behind `REDDIT_FETCH_MODE`:
  `rss` (public `/r/<sub>/new/.rss` feeds — no credentials, but unofficial, undocumented, and
  returns no post body) for local dev while approval is pending, and `api` (asyncpraw, read-only
  OAuth) for production. Both emit the same dict shape, so switching is a config change.
  **RSS is dev-only** — `docs/ARCHITECTURE.md` §8's "no scraping fallback" commitment stands, and
  shipping on an endpoint Reddit could silently kill is not acceptable for a paid product.

  Deferred on purpose: pushing ingested posts onto the Redis queue for the embedding worker — that
  consumer doesn't exist yet (same reasoning as the deferred worker services above). `arq` was
  added as a dependency now in anticipation.

  Verified end-to-end: migration applies, `ruff` + 12 `pytest` tests pass, and a live run in RSS
  mode against a seeded `r/forhire` watcher fetched and stored 25 real posts with correct
  title/author/permalink/timestamp parsing, then re-polled without creating duplicates.

  Two incidental fixes along the way: (1) `REDIS_URL` was being passed to the `api` container by
  compose but never declared in `Settings`, so it was silently dropped — now declared. (2) The
  compose Postgres published on host port 5432, which collides with the locally-installed
  PostgreSQL 18 Windows service on this machine (host connections silently reached the wrong
  database, failing auth); it now publishes on `${POSTGRES_HOST_PORT:-5433}`. Container-to-
  container traffic was never affected, which is why the previous session's verification passed.
  Also note `uv` was **not** actually present on this machine despite the previous log entry
  claiming it was installed — it was reinstalled into a throwaway venv to regenerate `uv.lock`.
- **2026-07-30**: Built the **embedding worker** (`backend/app/workers/embed.py` +
  `embedding_source.py`). Full walkthrough in `docs/embedding-worker/`. Migration `b7e1f3c9d024`
  adds `reddit_posts.embedding` and `watchers.intent_embedding` (both `VECTOR(1536)`, nullable),
  matching `embedded_at` columns, partial indexes on the NULL rows for the sweep's hot query, and an
  HNSW `vector_cosine_ops` index on the **watcher** side only — the matcher searches watchers per
  incoming post, and indexing the constantly-inserted `reddit_posts` would cost write throughput for
  no current reader.

  Runs as an Arq consumer (`arq app.workers.embed.WorkerSettings`, service `worker-embed`) with
  **two triggers**: jobs enqueued by the ingestion worker the moment a post is inserted, plus a cron
  backfill sweep over rows still `NULL`. The sweep is not redundant — it covers posts stored before
  the worker existed, jobs that exhaust `max_tries`, and watcher intents (which have no CRUD API yet
  to enqueue from, so today the sweep is their *only* trigger). Commit happens once per batch after
  the API returns, so a mid-batch failure leaves rows `NULL` and the sweep retries them; that was
  verified, not assumed.

  Ingestion's deferred queue hand-off is now wired: `store_posts` returns the inserted ids instead of
  a count, and `enqueue_for_embedding` pushes one `embed_post` job each with `_job_id` derived from
  the post id so duplicate enqueues are no-ops. Both a missing Redis at startup and a failing
  individual enqueue are logged and survived rather than fatal.

  **Decision: no offline/fake embedding mode in the runtime.** A config-selectable fake provider was
  planned (mirroring `REDDIT_FETCH_MODE`) and deliberately dropped: fake vectors carry no semantic
  meaning, so a keyless pipeline would prove the plumbing moves data while proving nothing about
  match quality, and it adds a path that could reach production by misconfiguration. The
  `EmbeddingProvider` protocol stays, and `FakeEmbeddingProvider` lives in `tests/conftest.py` so
  tests exercise real worker code paths with no key, no network, and no spend.

  `EMBEDDING_DIMENSIONS` (1536) lives in `app/core/constants.py` as a constant, not a setting — it is
  baked into the pgvector column type, so changing it requires a migration plus a full re-embed.
  Also kept in `core` rather than a worker module so `app.models` never imports from `app.workers`.

  Verified: `ruff` clean, **43 pytest tests pass** (up from 12), migration applied against the live
  compose Postgres (schema and all three indexes confirmed via `\d`), `docker compose build
  worker-embed` succeeds, and the container fails on a missing key with the intended actionable
  message and exit code 1. The real worker also booted against live Postgres + Redis, fired its
  startup sweep, correctly picked watchers before posts, and reached the OpenAI call — which failed
  with a deliberate invalid key. The 25 stored posts and 1 watcher were confirmed still `NULL`
  afterwards, proving the retry path.

  **Live run completed** with a real key: `docker compose up worker-embed` embedded 1 watcher and
  all 25 posts on the startup sweep — 483 tokens, ~$0.00001, 25 distinct vectors (confirmed not
  degenerate). The embedding worker is now fully verified end to end.

  **First real matching signal — and it confirms the core product risk.** A cosine-similarity query
  against the seeded watcher (`intent_text`: "someone looking to hire a developer") ranked
  **`[FOR HIRE]` posts — people offering services — above the actual `[Hiring]` posts**:

  | similarity | title |
  |---|---|
  | 0.627 | `[FOR HIRE] Full Stack Laravel Developer with 3+ Years Experience` |
  | 0.583 | `[FOR HIRE] Flutter Full-Stack Developer` |
  | … | … |
  | 0.531 | `[Hiring] Commission-only closers for a SaaS` |
  | 0.514 | `[HIRING] Mobile App Growth Specialist` |

  This is exactly the needs-vs-offers false-positive problem [[PRD]] §1 names as the reason the
  product needs two-stage matching, now observed on real data rather than assumed. Embedding
  similarity alone would rank this watcher's feed almost exactly backwards. It is strong empirical
  support for the locked decision to make the **LLM verifier the actual precision gate**, with the
  vector stage tuned purely for recall.

  Precise reading of that table: of the 25 posts, **5 are requests** (`[Hiring]`-tagged) and 20 are
  offers, and *none* of the 5 is actually hiring a developer — they want a print-file editor, sales
  closers, two marketers, and a PNG→SVG conversion. So the correct end-to-end result for this
  watcher is **zero matches**, and raw similarity instead surfaced six wrong-direction posts above
  every request, at a confident-looking 0.51–0.63. The failure is not "true matches rank low", it is
  "there are no true matches and the vector stage is confident anyway".

  Second observation, feeding the open matcher-gate decision: every score sat in that narrow
  **0.51–0.63** band with no separation between right and wrong answers, so a fixed similarity
  threshold would be close to useless — **top-K per post is the right gate shape**, matching
  [[ARCHITECTURE]]'s reasoning.

  **Follow-up experiment (2026-07-30): how to fix the direction failure.** Three query-construction
  strategies were tested over the same 25 posts across 3 different watcher intents. Scripts are
  throwaway (scratchpad), results summarised here.

  | strategy | requests in top 5 (dev / logo / ads) | notes |
  |---|---|---|
  | raw intent text (current code) | 0/5, 1/5, 2/5 | systematically anti-correlated |
  | hypothetical example post (HyDE) | 0/5 | no better than raw — **hypothesis failed** |
  | per-watcher contrastive (want − avoid) | 5/5, 4/5, 4/5 | strongest, but **suppressed a true match** (a true ad-work post fell rank 1 → 11 because the anti-example reused its wording) |
  | **global direction axis** (see below) | 2/5, 2/5, 4/5 | milder, but **never suppressed a true match**; both true matches improved (logo 5→1, ads 3,1→2,1) |

  The global axis is computed once from topic-free phrasings:
  `d = normalise(mean(generic "I am available for hire" texts) − mean(generic "we need to hire
  someone" texts))`, then `score = cos(intent, post) − λ·(post̂ · d)` with λ≈1.0–1.5. Because it
  encodes direction only and no topic, it cannot suppress a true match the way a bespoke
  anti-example can.

  **Conclusion for the matcher build**: use the global direction axis in the vector gate, *not* the
  per-watcher contrastive. For a recall-favouring gate feeding an LLM verifier, "never suppresses a
  true match" beats "separates best on average" — a false negative here is silent and unrecoverable,
  a false positive costs one cheap LLM call. Also: reject a regex on `[Hiring]`/`[FOR HIRE]` tags as
  the foundation — the tags were reliable in this sample, but they exist on only a handful of
  subreddits and would not generalise. Fine as a per-subreddit bonus signal later.

  Caveat on all of the above: n=25, one subreddit, titles only (RSS mode), 3 hand-written intents.
  This is directional evidence for *design*, not calibration data. Re-run once `api`-mode data with
  real post bodies exists — bodies carry most of the "I need" vs "I offer" phrasing that titles
  compress away, so the whole problem may soften.
- **2026-07-30**: Built the **matcher + LLM verifier** (`backend/app/workers/match.py`,
  `direction.py`, `verifier.py`). Full walkthrough in `docs/matcher/`. Migration `c3f8a1b56e42`
  adds `watchers.direction` (default `requesting`) and the `matches` table, with partial indexes for
  the verification queue (`llm_verified IS NULL`) and the future notification queue
  (`llm_verified IS TRUE AND notified_at IS NULL`).

  Runs as an Arq consumer (`arq app.workers.match.WorkerSettings`, service `worker-match`), with the
  same two triggers as the embedding worker: a job enqueued the moment a post's vector is committed,
  plus a cron backfill sweep. The embedding worker's hand-off enqueues **after** the commit, so the
  matcher can never load a row that isn't there — asserted by a test on call ordering.

  **The direction axis is the fix for the needs-vs-offers problem**, implemented as the global
  topic-free variant chosen in the experiment above:
  `d = normalise(mean(offer phrasings) − mean(request phrasings))`, computed once at startup from one
  embedding call, then `adjusted = cosine(intent, post) − weight × penalty`. The penalty is
  **one-sided** — a wrong-direction post is pushed down, a right-direction post gets no bonus, since
  rewarding direction would let a topically irrelevant post outrank a well-matched one.

  **Correction to the experiment's framing, found while implementing.** The experiment ranked *posts
  for one watcher*; the matcher ranks *watchers for one post*. A post's direction score is a single
  number, so among watchers that all want the same side it is a constant offset and **cannot
  reorder them**. Its two real jobs are separating watchers that want opposite sides (where it does
  rerank, correctly) and pushing a whole candidate set down so an absolute floor becomes meaningful.
  Both behaviours have tests, including the negative case that same-direction watchers are *not*
  reordered — so the limitation is pinned rather than assumed. This is why a similarity floor is now
  an explicit open decision above.

  **Verifier**: `claude-haiku-4-5` per [[ARCHITECTURE]] §5, one yes/no call per candidate, JSON reply.
  The prompt demands three things — direction, subject, and substance — and explicitly tells the
  model to judge direction from what the poster is *doing*, not from tags, because posters mislabel
  their own posts. Ties go to `false`. Two failure paths are deliberate: a `stop_reason: "refusal"`
  raises rather than recording a rejection the model never made, and an unreadable `matches` value
  raises rather than being coerced — `bool("false")` is `True` in Python, so a quoted `"false"` would
  otherwise have been stored as a match. Either way the row stays `NULL` for the sweep to retry.

  **Every candidate is written to `matches`, pass or fail**, with its similarity, direction score,
  adjusted score, and the verifier's reason. The rejected rows are the point — that is the labelled
  dataset that finally calibrates K and the floor, cheap to collect now and impossible to
  reconstruct later.

  Verified: `ruff` clean, **112 pytest tests pass** (up from 43), migration applied to the live
  compose Postgres (schema, both partial indexes, and the existing watcher backfilled to
  `requesting`), `uv.lock` regenerated with `anthropic 0.120.2`, `docker compose build worker-match`
  succeeds, and the container fails on a missing key with the intended message and exit code 1.

  The **vector gate was also run live against all 25 embedded posts** (verifier stubbed out, since
  there is no Anthropic key yet): the axis computed, the candidate query found the seeded watcher,
  ranking produced sane scores, and re-running the gate over the same post wrote 0 rows — the
  `ON CONFLICT` idempotency holds in practice, not just in theory. The direction signal held up on
  real data with no topic leakage: **every `[Hiring]` post scored negative** (−0.098 to −0.036) and
  the `[FOR HIRE]` posts mostly positive. Magnitudes are ~±0.1 against similarities of ~0.5, so at
  `weight=1.0` it is a nudge — which is the intended strength for a recall-favouring gate.

  **Not yet done: one live run with a real `ANTHROPIC_API_KEY`** — the only unverified step. `.env`
  and `backend/.env` have an empty `ANTHROPIC_API_KEY=` line ready to fill.
- **2026-07-30**: Built **users, Clerk auth, and watcher CRUD** (backend only). Full walkthrough in
  `docs/auth-and-watchers/`. Migration `d4a9c2e71f38` creates `users` and adds `watchers.user_id`
  (NOT NULL, FK, cascade). Endpoints: `GET /me`, and full CRUD on `/watchers`.

  **The migration deletes data.** `user_id` is NOT NULL and pre-existing watchers have no owner to
  assign, so the upgrade runs `DELETE FROM watchers` (their `matches` rows cascade). At the time
  that meant one seeded dev watcher. On a database with real watchers this needs a different
  strategy.

  Auth uses the official `clerk-backend-api` SDK's `verify_token_async` — RS256 against Clerk's
  JWKS, expiry enforced. 401 (with `WWW-Authenticate`) for bad tokens with the *reason logged, not
  returned*; 500 with an actionable message when `CLERK_SECRET_KEY` is unset, because that is our
  misconfiguration rather than the caller's bad credentials.

  **Account rows are created just-in-time, not by a webhook.** This is a deliberate deferral with a
  concrete cost: without a `user.deleted` webhook, a deleted Clerk account leaves its `users` row and
  its watchers `active`, so **the ingestion worker keeps polling and the embedding worker keeps
  spending on someone who no longer exists**. Fine at zero users, must not ship to production —
  now an explicit milestone above.

  Three decisions worth recording:

  - **Ownership violations return 404, not 403.** A 403 confirms the id exists, which would let
    someone enumerate other users' watchers.
  - **Subreddit names are normalised to lowercase with `r/` stripped**, and this is load-bearing
    rather than cosmetic: the ingestion worker polls these exact strings and the matcher does an
    exact-string `subreddits.any(post.subreddit)`. Mixed casing would double-poll *and* silently
    fail to link posts to one of the two watchers.
  - **Editing `intent_text` clears `intent_embedding` in the same transaction** rather than only
    enqueueing a re-embed. Enqueueing alone leaves a window where the matcher compares posts against
    the *old* wording; clearing it makes the matcher skip the watcher (it requires a non-NULL
    embedding) until the embedding worker catches up. Renames and subreddit edits deliberately do
    **not** clear it.

  **The test story changed.** CRUD needs real Postgres — pgvector, `ARRAY`, and UUID rule out
  SQLite, and the FK cascades and tier queries are what is worth testing. DB-backed tests are marked
  `db` and **skip automatically** when Postgres is unreachable, so a plain `pytest` still passes with
  no services running; `pytest -m db` with compose up runs them for real. Each runs in a transaction
  rolled back at teardown. The availability probe is memoised per session — probing an unreachable
  host once per test turned a 4-second suite into a 100-second one.

  Verified: `ruff` clean (added a narrow `flake8-bugbear.extend-immutable-calls` entry for FastAPI's
  `Depends`, rather than switching B008 off), **199 tests pass** — 175 with no services, 199 with
  Postgres up — migration applied live, `uv.lock` regenerated with `clerk-backend-api 6.0.1`, and the
  API booted under `docker compose` with the new lifespan: `/api/v1/health` OK, all seven routes in
  the OpenAPI schema, 401 for missing and malformed `Authorization` headers, and the intended 500
  naming `CLERK_SECRET_KEY` when it is unset.

  **Not yet done: an authenticated request with a real Clerk token.** `CLERK_SECRET_KEY` is empty in
  `.env` and `backend/.env` — it is the same value as `frontend/.env.local`'s, which was not copied
  across without asking.
- **2026-07-30**: Built the **watcher management UI** (`/frontend`). Full walkthrough in
  `docs/watcher-ui/`. The dashboard now loads `/me` and `/watchers`, creates watchers, and
  pauses/resumes/deletes them.

  **Read `node_modules/next/dist/docs/` first**, per `frontend/AGENTS.md`. Three things in
  Next 16.2.11 differ from older App Router conventions and would have been written wrong from
  memory:

  - **`fetch` is uncached by default** (earlier versions cached it), so per-user API calls need no
    `cache: "no-store"` — and adding `use cache` anywhere on that path would leak one user's data
    to another.
  - **`refresh()` from `next/cache`** is the post-mutation tool, callable only inside a Server
    Action. `revalidatePath`/`revalidateTag` target Next's own data cache, which this app never
    populates — its data lives in FastAPI.
  - **Cache Components** (`use cache` / `cacheLife`) is opt-in via `cacheComponents: true` and is
    not enabled here.

  Design decisions worth recording:

  - **Every API call is server-side** (Server Components + Server Actions). The Clerk token never
    enters the browser bundle — `lib/api.ts` starts with `import "server-only"` so importing it
    from a Client Component is a build error, not a runtime leak — and CORS never applies, because
    the request is Node → FastAPI.
  - **The server-side base URL is deliberately not the `NEXT_PUBLIC_` one.** That value is inlined
    into the browser bundle at build time and points at `localhost`, which is the wrong host from
    inside a container; `API_BASE_URL` takes precedence.
  - **Every Server Action re-checks auth.** Server Functions are reachable by direct POST, not only
    through the UI that rendered them, so a check on the page protects nothing.
  - **Plan limits are not duplicated client-side.** The form stays enabled at the cap and the API's
    own 409 message explains it. `GET /me` exists so the tier table has one home; a second
    implementation in the browser could disagree with it and is bypassable anyway.
  - **A 409 is state, not an exception** — it renders next to the form rather than hitting an error
    boundary, because hitting your plan limit is a normal outcome. Non-API errors still throw.

  Verified: `npm run lint` and `npm run build` both clean (`/dashboard` correctly dynamic), the API
  running with a real Clerk secret returns 401 + `"Invalid or expired token"` for a forged token —
  which proves `verify_token_async` is reaching Clerk's JWKS rather than failing earlier — and a
  signed-out `/dashboard` 307s to `/sign-in?redirect_url=…` with no errors in the dev log.

  **Not yet done: the signed-in round trip.** It needs a human to sign in through a browser, which
  cannot be done headlessly. Everything up to that point is verified. Note the API was started with
  `CLERK_SECRET_KEY` passed as a one-off environment variable sourced from `frontend/.env.local`;
  it is still empty in `.env` and `backend/.env`, so a plain `docker compose up api` will not have
  it. Note that host-side runs
  (outside Docker) also need `OPENAI_API_KEY` in `backend/.env`; only the root `.env` is filled in
  today, which is why the gate check above had to source the key explicitly. One candidate row is
  currently sitting in `matches` with `llm_verified` NULL from that check — the sweep will judge it
  as soon as a key exists.

  Note on tooling: `uv` **cannot execute on this machine at all** — `pip install uv` succeeds, but
  running the binary is blocked by a Windows Application Control policy (`WinError 4551`), from both
  the `python -m uv` shim and the `uv.exe` in `%APPDATA%\Python\Python314\Scripts`. This supersedes
  the 2026-07-26 note claiming uv was installed. Two workarounds now in use, both repeatable:

  - **Running tests/lint/alembic locally**: bootstrap `pip` into `backend/.venv` with
    `python -m ensurepip`, then use `.venv\Scripts\python.exe -m pytest` / `-m ruff` / `-m alembic`
    directly. The CLAUDE.md `uv run ...` commands do not work here.
  - **Regenerating `uv.lock`** (needed whenever `pyproject.toml` changes, since the Dockerfile's
    `uv sync --frozen` fails on a stale lock): run uv in a container —
    `docker run --rm -v "<repo>\backend:/w" -w /w python:3.12-slim sh -c "pip install uv && uv lock"`.
    The official `ghcr.io/astral-sh/uv` image does **not** work for this (it cannot determine libc
    on its own). `uv.lock` was regenerated this way and now includes `openai` and its four new
    transitive deps.

- **2026-07-31**: Built the **match feed** — API and UI. Full walkthrough in `docs/match-feed/`.
  This closes the product loop: the matcher has been writing confirmed matches since 2026-07-30 and
  nothing in the product read them.

  Endpoints: `GET /matches` (paged), `POST /matches/{id}/read`, `POST /matches/read-all`, plus
  `unread_matches` added to `GET /me` so the nav badge costs no extra request.

  Decisions worth recording:

  - **Only `llm_verified IS TRUE` appears.** Written `.is_(True)`, not a truthiness test: the column
    is three-valued, and NULL ("the verifier has not run") must be excluded as firmly as False. A
    pending candidate is an unknown, not a weak match.
  - **Sorted by `matches.created_at`, not the post's `posted_at`.** `posted_at` is nullable — the
    RSS fetch mode does not always supply it — so it cannot be a sort key without a `COALESCE` that
    defeats the index.
  - **Cursor paging, not OFFSET.** Matches arrive at the head of this feed continuously, and every
    insert shifts an OFFSET window by one. The `id` is part of the sort key because Postgres' `now()`
    is transaction start time and the matcher writes a batch in one transaction — sibling rows
    genuinely share a `created_at`, and paging on the timestamp alone would drop some of them.
  - **Scores are not exposed.** `similarity`, `direction_score`, `adjusted_score` stay server-side:
    a cosine of 0.62 reads as "62% confident" and is nothing of the sort. `llm_reason` *is* shown —
    a match that states its reasoning is checkable, which the eventual feedback loop needs.
  - **Ownership is a join.** `matches` has no `user_id`; the only link is `matches → watchers.user_id`.
    `?watcher_id=` narrows an already user-scoped query rather than replacing the scope — the other
    way round would let anyone read anyone's feed by guessing an id.
  - **The feed does not call `refresh()`**, unlike every mutation in `docs/watcher-ui/`. It holds
    loaded pages in client state, and re-rendering the route would discard them. Other routes stay
    correct because dynamic pages have a zero client-cache stale time (since Next 15).
  - **Two partial indexes** (`ix_matches_feed`, `ix_matches_unread`), partial because rejected and
    unverified candidates are the bulk of the table.
  - **Four empty states, not one** — no watchers / all paused / still embedding / active but nothing
    matched. The pipeline takes minutes to reach a new watcher, and one generic message makes the
    correct state indistinguishable from a broken app.

  Verified: **218 tests pass** including 30 new DB-backed ones, `ruff` clean, `npm run lint` and
  `npm run build` clean with `/matches` correctly dynamic, signed-out `/matches` 307s to sign-in,
  and the full feed exercised against real Postgres through seeded data — paging across three
  pages, mark-read, and the unread count on `/me` all confirmed. Seeded rows and the temporary user
  were removed afterwards; the dev database is back to zero users and zero matches.

  Added `backend/scripts/seed_matches.py` (dev-only, mounted into the api container rather than
  baked into the image) so the UI can be exercised before `ANTHROPIC_API_KEY` exists. It refuses to
  run outside a local environment and `--clear` removes only its own rows, found by a `seed_`
  prefix.

  **Tooling change — the host venv can no longer run the test suite at all.** The Windows
  Application Control policy has tightened since 2026-07-30: it now blocks `_ctypes.pyd` in the
  uv-managed CPython, so anything importing `asyncpg` dies with `ImportError: DLL load failed while
  importing _ctypes`. That is every DB test, plus alembic. This supersedes the "bootstrap pip into
  backend/.venv" workaround above. **Run tests, ruff and alembic in a container instead**:

  ```
  docker run --rm --network postping_default -v "<repo>\backend:/w" -w /w \
    -e UV_PROJECT_ENVIRONMENT=/opt/venv \
    -e DATABASE_URL="postgresql+asyncpg://postgres:postgres@postgres:5432/postping" \
    python:3.12-slim sh -c "pip install uv && uv sync --frozen && /opt/venv/bin/pytest"
  ```

  `UV_PROJECT_ENVIRONMENT` matters: without it `uv sync` writes `.venv` into the mounted directory
  and clobbers the host's Windows venv. Add `--ignore EXE002` when running ruff this way — every
  file looks executable across a Windows bind mount, which is a mount artifact, not a finding.
