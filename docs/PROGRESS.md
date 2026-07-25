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
- [ ] Exact initial value for the matcher's similarity gate/K — deferred by design until there's
      real ingestion data to calibrate against (see [[ARCHITECTURE]] Matcher section)

## Milestones

- [x] Brainstorm core idea, tech stack direction
- [x] Lock product-shape decisions (audience, monetization, watcher scoping, notification
      channels, dashboard, feedback loop timing, tier differentiation)
- [x] Write PRD, Features, Architecture, Workflow docs
- [ ] Resolve open decisions above
- [x] Scaffold `/backend` (FastAPI project structure, Docker)
- [x] Scaffold `/frontend` (Next.js project structure, Docker)
- [ ] `docker-compose.yml` for local dev (api, workers, postgres+pgvector, redis, frontend)
- [ ] Reddit API app registration + credentials
- [ ] Ingestion worker MVP (poll → dedupe → queue)
- [ ] Embedding worker MVP
- [ ] Matcher + LLM verifier MVP
- [ ] Notification worker MVP (email + Telegram)
- [ ] Watcher CRUD API + UI
- [ ] Match dashboard UI
- [ ] Auth wired end-to-end
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
