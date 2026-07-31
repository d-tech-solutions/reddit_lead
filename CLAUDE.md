# PostPing

Reddit intent-alert SaaS: users create "watchers" (subreddits + a plain-language description of
the kind of request they want to catch), and the app notifies them when a matching post appears.

**Status**: ingestion, embedding, and matcher/LLM-verifier workers built. Auth (Clerk) + watcher
CRUD built end to end, API and UI. Match feed built end to end (API + UI). Notification worker not
started.

## Start here

Before making any product or architecture decision, read `/docs`:

- `docs/PRD.md` — problem, target users, tiers/pricing, MVP scope, risks
- `docs/FEATURES.md` — feature list by phase (MVP / Phase 2 / Phase 3)
- `docs/ARCHITECTURE.md` — pipeline design, tech stack, data model, deployment, monitoring
- `docs/WORKFLOW.md` — user and system sequence flows
- `docs/PROGRESS.md` — decisions already locked in, open items, milestone checklist — check this
  first to avoid re-litigating settled decisions
- `docs/ingestion-worker/`, `docs/embedding-worker/`, `docs/matcher/`, `docs/auth-and-watchers/`,
  `docs/watcher-ui/`, `docs/match-feed/` — code-level walkthroughs. Each built component gets its
  own `docs/<component-name>/` folder.

## Locked decisions (see docs/PROGRESS.md for the full list)

Stack: FastAPI (`/backend`) + Next.js (`/frontend`), Postgres+pgvector, Redis+Arq, Clerk (auth),
Resend (email), Docker/docker-compose (no Kubernetes yet). Full reasoning lives in
`docs/ARCHITECTURE.md` — don't re-derive it here.

## Dev commands

Full stack: `docker compose up --build` (postgres on host port **5433**, api 8000, frontend 3000).

Backend (`/backend`, uses **uv**):

```
uv sync                       # install deps
uv run pytest                 # tests
uv run ruff check .           # lint
uv run alembic upgrade head   # apply migrations
uv run alembic revision --autogenerate -m "..."
uv run uvicorn app.main:app --reload
python -m app.workers.ingest  # ingestion worker
```

Frontend (`/frontend`, uses **npm**): `npm run dev` / `npm run lint` / `npm run build`.

## Reddit data source

`REDDIT_FETCH_MODE` selects how the ingestion worker fetches posts:

- `rss` — public `.rss` feeds, no credentials. **Local dev only**: unofficial, no post bodies.
- `api` — official read-only OAuth via asyncpraw. **Required for production.**

Official API access needs manual approval under Reddit's Responsible Builder Policy and is not
yet granted — see `docs/PROGRESS.md`. Do not propose scraping as a workaround
(`docs/ARCHITECTURE.md` §8).

## Rules for Claude

**Never run git commands.** No `git add`, `commit`, `push`, `checkout`, `branch`, `stash`, `reset`,
`rebase`, etc. — not even read-only ones like `git status` or `git log`. Version control is handled
manually. If a task seems to need git, describe the commands and let the user run them.

**Every function gets a one- or two-line comment directly above its definition** — above the
`def`/`async def` in Python, above the function in TypeScript/JavaScript. Not a docstring or
JSDoc block inside or below the signature. Say what the function does and why it exists, not a
restatement of its name.

```python
# Pull posts from a subreddit newer than `since`, using whichever fetch mode is configured.
# Returns oldest-first so the ingest cursor advances cleanly.
async def fetch_new_posts(subreddit: str, since: datetime) -> list[RedditPost]:
    ...
```

## Keeping this file and docs in sync

This file is intentionally thin. Once scaffolding starts, extend it with actual dev commands
(run/test/lint), folder structure, and any conventions that emerge — but keep product/architecture
rationale in `/docs`, not here. Update `docs/PROGRESS.md` as milestones complete.
