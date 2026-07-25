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
- Free and Paid tiers get the same matching speed; tiers differ on watcher count, subreddits per
  watcher, and notification channels
- Two-stage matching (vector similarity retrieval + LLM intent verification) to solve the
  needs-vs-offers false positive problem
- Stack: FastAPI (`/backend`) + Next.js (`/frontend`), Postgres+pgvector, Redis, Docker/
  docker-compose for MVP scale (no Kubernetes yet)

## Open decisions (not yet locked)

- [ ] Exact free-tier vs. paid-tier numeric limits (watcher count, subreddits per watcher)
- [ ] Paid tier pricing (dollar amount)
- [ ] Auth provider: Clerk vs. Auth0 vs. Supabase Auth vs. custom
- [ ] Email provider: Resend vs. SES vs. other
- [ ] Product name (currently placeholder "PostPing")
- [ ] Initial similarity threshold value for the matcher (will need empirical tuning once real
      data flows)
- [ ] Task queue library: Arq vs. Dramatiq vs. Celery

## Milestones

- [x] Brainstorm core idea, tech stack direction
- [x] Lock product-shape decisions (audience, monetization, watcher scoping, notification
      channels, dashboard, feedback loop timing, tier differentiation)
- [x] Write PRD, Features, Architecture, Workflow docs
- [ ] Resolve open decisions above
- [ ] Scaffold `/backend` (FastAPI project structure, Docker)
- [ ] Scaffold `/frontend` (Next.js project structure, Docker)
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
