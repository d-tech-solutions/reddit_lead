# PostPing

Reddit intent-alert SaaS: users create "watchers" (subreddits + a plain-language description of
the kind of request they want to catch), and the app notifies them when a matching post appears.

**Status**: ingestion and matcher/LLM-verifier workers built. Auth (Clerk) + watcher CRUD built end
to end, API and UI. Match feed built end to end (API + UI). Notification worker not started.

## Start here

Before making any product or architecture decision, read `/docs`:

- `docs/PRD.md` — problem, target users, tiers/pricing, MVP scope, risks
- `docs/ARCHITECTURE.md` — pipeline design, tech stack, data model, deployment, monitoring
- `docs/WORKFLOW.md` — user and system sequence flows
- `docs/ingestion-worker/`, `docs/matcher/`, `docs/auth-and-watchers/`, `docs/watcher-ui/`,
  `docs/match-feed/` — code-level walkthroughs. Each built component gets its own
  `docs/<component-name>/` folder.

## Locked decisions (see docs/PROGRESS.md for the full list)

Stack: FastAPI (`/backend`) + Next.js (`/frontend`), Postgres+pgvector, Redis+Arq, Clerk (auth),
Resend (email), Docker/docker-compose (no Kubernetes yet). Full reasoning lives in
`docs/ARCHITECTURE.md` — don't re-derive it here.

## Dev commands

Full stack: `docker compose up --build` (postgres on host port **5433**, api 8000, frontend 3000).

Backend (`/backend`, uses **uv**):

```
uv sync                       # install deps
uv run pytest                 # tests (DB-backed ones skip if Postgres isn't up)
uv run pytest -m db           # only the tests needing a live Postgres
uv run ruff check .           # lint
uv run alembic upgrade head   # apply migrations
uv run alembic revision --autogenerate -m "..."
uv run uvicorn app.main:app --reload
python -m app.workers.ingest              # ingestion worker (own process, interval loop)
arq app.workers.match.WorkerSettings      # matcher + LLM verifier (Arq consumer)
```

**On this machine none of those backend commands run on the host.** A Windows Application Control
policy blocks the `uv` binary *and* `_ctypes.pyd` in the uv-managed CPython, so anything importing
`asyncpg` — every DB test, plus alembic — dies with `ImportError: DLL load failed while importing
_ctypes`. Run them in a container instead:

```
docker run --rm --network postping_default -v "<repo>\backend:/w" -w /w \
  -e UV_PROJECT_ENVIRONMENT=/opt/venv \
  -e DATABASE_URL="postgresql+asyncpg://postgres:postgres@postgres:5432/postping" \
  python:3.12-slim sh -c "pip install uv && uv sync --frozen && /opt/venv/bin/pytest"
```

Swap the last command for `/opt/venv/bin/ruff check --ignore EXE002 .` or
`/opt/venv/bin/alembic upgrade head`. `UV_PROJECT_ENVIRONMENT` is not optional — without it
`uv sync` writes `.venv` into the mounted directory and clobbers the host's Windows venv. The
`EXE002` ignore is because every file looks executable across a Windows bind mount. From Git Bash,
prefix docker commands with `MSYS_NO_PATHCONV=1` or `-w /w` is rewritten to `W:/`.

Dev-only helper: `docker compose exec api python -m scripts.seed_matches --email you@example.com`
writes fake confirmed matches so the feed UI works without live API keys (`--clear` removes them).

Frontend (`/frontend`, uses **npm**): `npm run dev` / `npm run lint` / `npm run build`.

**Next.js 16 differs from older App Router conventions** — `frontend/AGENTS.md` requires reading
`node_modules/next/dist/docs/` before writing frontend code. The ones that have bitten already:
`fetch` is uncached by default, post-mutation refresh is `refresh()` from `next/cache` (Server
Actions only), Cache Components (`use cache`) is opt-in and off, and middleware lives in `proxy.ts`.

## Reddit data source

`REDDIT_FETCH_MODE` selects how the ingestion worker fetches posts:

- `rss` — public `.rss` feeds, no credentials. **Local dev only**: unofficial, no post bodies.
- `api` — official read-only OAuth via asyncpraw. **Required for production.**

Official API access needs manual approval under Reddit's Responsible Builder Policy and is not yet
granted. Do not propose scraping as a workaround (`docs/ARCHITECTURE.md` §8).

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
rationale in `/docs`, not here.
