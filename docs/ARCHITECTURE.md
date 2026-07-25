# Architecture

Companion to [[PRD]] and [[FEATURES]]. Covers system design, tech stack, data model, deployment,
and monitoring for Phase 1 (MVP), with notes on what changes in later phases.

## 1. High-level pipeline

```mermaid
flowchart LR
    Reddit[(Reddit API)] --> Ingest[Ingestion Worker]
    Ingest --> Queue[[Redis Queue]]
    Queue --> Embed[Embedding Worker]
    Embed --> VDB[(Postgres + pgvector)]
    VDB --> Match[Matcher: post vs watcher embeddings]
    Match -->|candidates above threshold| Verify[LLM Intent Verifier]
    Verify -->|confirmed match| Notify[Notification Worker]
    Notify --> Email[Email]
    Notify --> Telegram[Telegram]
    Match --> DB[(Postgres: matches table)]
    Notify --> DB
    API[FastAPI] <--> DB
    Frontend[Next.js] <--> API
```

Each stage is a separate worker process so it can be scaled independently in Docker (ingestion is
rate-limited by Reddit; embedding/LLM stages are cost-sensitive; notification is bursty).

## 2. Why this shape (recap of key decisions)

- **Watchers are scoped to specific subreddits** (not all of Reddit) — bounds ingestion volume,
  keeps embedding/LLM cost predictable, matches Reddit API rate limits. See [[PRD]] §8.
- **Two-stage matching** (vector similarity → LLM verification) exists specifically to solve the
  "offers vs. needs" false-positive problem described in [[PRD]] §1 — embedding similarity alone
  cannot distinguish intent direction reliably.
- **pgvector inside Postgres**, not a separate vector DB, for MVP — one datastore to operate, and
  watcher count (the side we query against) stays small even as post volume grows, so pgvector's
  performance ceiling is not a near-term concern.
- **Same matching speed for free and paid** (per PRD tier decision) — the ingestion/matching
  pipeline runs once, uniformly; tier logic only gates watcher count, subreddit count, and
  notification channels at the API layer.

## 3. Components

### Ingestion Worker
- Uses `asyncpraw` (async Reddit API client) with OAuth "script" app credentials
- Polls the distinct set of subreddits across all *active* watchers (union, not per-watcher — one
  post insert can match multiple watchers)
- Poll interval and Reddit's ~100 QPM-class rate limit are the primary scaling constraint on total
  subreddit coverage — tracked as a scaling question in [[PROGRESS]]
- Dedupes by Reddit post ID before pushing to the queue
- Emits a heartbeat on every successful poll cycle (used by uptime monitoring, see §7)

### Embedding Worker
- Consumes new posts from the queue
- Calls the embedding model (OpenAI `text-embedding-3-small` for MVP) on title + body
- Writes post + embedding to Postgres (pgvector column)

### Matcher
- On each new post embedding, runs a similarity search against the embeddings of *active
  watchers whose subreddit list includes this post's subreddit*
- Returns candidates using a **recall-favoring gate**, not a precisely-tuned threshold: either a
  deliberately loose similarity cutoff, or a top-K nearest watchers per post (K bounds LLM cost
  directly, sidestepping the need to guess a score). Since the LLM verifier is the actual
  precision gate (§ below), this stage only needs to avoid discarding true matches — a false
  negative here is silent and unrecoverable, whereas a false positive just costs one extra LLM
  call.
- The gate value (threshold or K) is a config value, not a hardcoded constant. From day one, log
  every candidate's similarity score alongside the LLM verifier's final verdict; once enough
  labeled examples accumulate from real traffic, use that distribution to calibrate the gate.
  Per-watcher tuning (rather than one global gate) is Phase 2, see [[FEATURES]].

### LLM Intent Verifier
- Runs only on candidates that clear the similarity threshold (keeps LLM call volume low)
- Cheap/fast model (Claude Haiku class) classifies: does this post represent someone requesting
  the described service, matching the watcher's intent description — yes/no
- Confirmed matches are written to the `matches` table and enqueued for notification

### Notification Worker
- Reads a confirmed match + the watcher's configured channels
- Sends email (via a transactional email provider) and/or Telegram (via bot API, using the
  chat ID the user linked at setup)
- Records delivery status against the match row

### FastAPI backend (`/backend`)
- User-facing REST API: auth, watcher CRUD, match feed/history, notification channel settings,
  billing webhook handling (Stripe)
- Enforces plan limits (watcher count, subreddits per watcher, channels) server-side
- Does **not** run the ingestion/matching pipeline in-process — that's the worker fleet, kept
  separate so the user-facing API stays responsive regardless of pipeline load

### Next.js frontend (`/frontend`)
- Auth screens, watcher management UI, match dashboard/inbox, notification settings, billing
  upgrade flow

## 4. Data model (MVP sketch)

```
users            (id, email, auth info, plan, created_at)
watchers         (id, user_id, name, intent_text, intent_embedding, subreddits[], status, created_at)
reddit_posts     (id, reddit_post_id, subreddit, title, body, author, embedding, fetched_at)
matches          (id, watcher_id, reddit_post_id, similarity_score, llm_verified bool, created_at, read_at)
notifications    (id, match_id, channel, status, sent_at)
notification_channels (id, user_id, type[email|telegram], config, verified bool)
subscriptions    (id, user_id, stripe_customer_id, plan, status)
```

Exact columns will firm up once the backend scaffolding starts; this is enough to drive API and
worker design.

## 5. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Backend API | FastAPI | `/backend` |
| Frontend | Next.js (App Router) | `/frontend` |
| Auth | Clerk | |
| Reddit client | asyncpraw | OAuth script app |
| Primary DB | Postgres + pgvector | Single datastore for MVP |
| Queue / broker | Redis + Arq | Async-native, lightweight vs. Celery |
| Embeddings | OpenAI `text-embedding-3-small` | Revisit self-hosted model at scale (Phase 3) |
| Intent verification | Claude Haiku-class model | Low-cost, only on candidates |
| Email | Resend | |
| Telegram | Bot API | |
| Billing | Stripe | |
| Error tracking | Sentry | FastAPI + Next.js SDKs |
| Metrics | Prometheus + Grafana | |
| Logs | structlog → Loki (or ELK) | |
| Containerization | Docker + docker-compose (dev/small prod) | K8s only if/when needed, see §6 |

## 6. Deployment

- **Local/dev**: `docker-compose.yml` with services: `api`, `worker-ingest`, `worker-embed`,
  `worker-match`, `worker-notify`, `postgres` (pgvector extension enabled), `redis`, `frontend`
- **Production (MVP scale)**: same compose topology on a single host or a managed container
  platform (Fly.io / Railway / a small ECS setup) — avoid Kubernetes until there's a concrete
  need for multi-node horizontal scaling of the worker fleet
- Workers are stateless and horizontally scalable independently (e.g. more `worker-embed`
  replicas if embedding becomes the bottleneck, without touching ingestion)
- Config/secrets via environment variables, `.env` for local dev (never committed)

## 7. Monitoring & observability

Motivated by the specific failure mode where a silent ingestion outage means a user gets zero
notifications and may not notice for days:

- **Sentry**: error tracking across FastAPI and Next.js
- **Prometheus + Grafana**: ingestion rate per subreddit, queue depth per stage, match rate,
  notification delivery latency, LLM/embedding API spend
- **Heartbeat/dead-man's-switch** (healthchecks.io or similar): ingestion worker pings on every
  successful poll cycle; missed pings alert immediately
- **Structured logs** (structlog) shipped to Loki/ELK, correlated by request/job ID across the
  pipeline stages
- **Cost tracking**: per-call logging of embedding/LLM spend, since cost scales with ingestion
  volume (Reddit traffic), not directly with paying-user count — called out as a risk in [[PRD]]

## 8. Security & compliance notes

- Reddit API usage must stay within official OAuth terms — no scraping fallback
- Store only what's needed from Reddit posts (avoid unnecessary retention of user-identifying
  Reddit data beyond what's needed to show/link the match)
- Stripe handles payment data directly (no card data touches our backend)
- Standard secrets hygiene: API keys/tokens in environment/secret manager, never in the repo

## 9. Open technical decisions

Tracked in [[PROGRESS]] — auth provider choice, exact free/paid numeric limits, email provider
choice, initial similarity threshold value.
