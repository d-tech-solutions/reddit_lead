# PostPing

Reddit intent-alert SaaS: users create "watchers" (subreddits + a plain-language description of
the kind of request they want to catch), and the app notifies them when a matching post appears.

**Status**: planning complete, no code written yet. `/backend` and `/frontend` don't exist yet.

## Start here

Before making any product or architecture decision, read `/docs`:

- `docs/PRD.md` — problem, target users, tiers/pricing, MVP scope, risks
- `docs/FEATURES.md` — feature list by phase (MVP / Phase 2 / Phase 3)
- `docs/ARCHITECTURE.md` — pipeline design, tech stack, data model, deployment, monitoring
- `docs/WORKFLOW.md` — user and system sequence flows
- `docs/PROGRESS.md` — decisions already locked in, open items, milestone checklist — check this
  first to avoid re-litigating settled decisions

## Locked decisions (see docs/PROGRESS.md for the full list)

Stack: FastAPI (`/backend`) + Next.js (`/frontend`), Postgres+pgvector, Redis+Arq, Clerk (auth),
Resend (email), Docker/docker-compose (no Kubernetes yet). Full reasoning lives in
`docs/ARCHITECTURE.md` — don't re-derive it here.

## Keeping this file and docs in sync

This file is intentionally thin. Once scaffolding starts, extend it with actual dev commands
(run/test/lint), folder structure, and any conventions that emerge — but keep product/architecture
rationale in `/docs`, not here. Update `docs/PROGRESS.md` as milestones complete.
