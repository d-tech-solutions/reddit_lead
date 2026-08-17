# Watcher UI (frontend)

Code-level walkthrough of the dashboard — the first frontend surface that talks to the API.
Companion to [[ARCHITECTURE]] §3 and `docs/auth-and-watchers/` (the API it calls).

**What it does, in one sentence**: lets a signed-in user see their plan usage, create watchers, and
pause or delete them.

## 1. Files involved

| File | Purpose |
|---|---|
| [`frontend/src/lib/api.ts`](../../frontend/src/lib/api.ts) | Server-only API client. Attaches the Clerk token, normalises errors. |
| [`frontend/src/lib/types.ts`](../../frontend/src/lib/types.ts) | TypeScript mirrors of the backend's Pydantic schemas. |
| [`frontend/src/app/actions/watchers.ts`](../../frontend/src/app/actions/watchers.ts) | Server Actions: create, set status, delete. |
| [`frontend/src/app/dashboard/page.tsx`](../../frontend/src/app/dashboard/page.tsx) | Server Component: loads `/me` + `/watchers`, renders the page. |
| [`frontend/src/components/watcher-form.tsx`](../../frontend/src/components/watcher-form.tsx) | Client Component: the create form, with pending state. |
| [`frontend/src/components/watcher-card.tsx`](../../frontend/src/components/watcher-card.tsx) | Client Component: one watcher plus its pause/delete controls. |

## 2. Next.js 16 notes

This project pins **Next 16.2.11**, and three of its behaviours differ from older App Router
conventions. `frontend/AGENTS.md` exists to force a docs read before writing code here; these are
the specific things that read turned up.

| Convention | What this version does |
|---|---|
| `fetch` caching | **Uncached by default.** Earlier versions cached `fetch` unless told otherwise, so per-user data needed `cache: "no-store"`. Here it is already correct, and adding `use cache` to anything on the API path would leak one user's data to another. |
| Post-mutation refresh | **`refresh()` from `next/cache`**, callable only inside a Server Action. It re-renders the route. `revalidatePath`/`revalidateTag` target Next's own data cache, which this app never populates — its data lives in FastAPI. |
| Cache Components | `use cache` / `cacheLife` is **opt-in** via `cacheComponents: true` and is **not enabled** here. |
| Middleware | Already handled before this milestone: Next 16 renamed `middleware.ts` to `proxy.ts`. |

## 3. Everything server-side

All API calls happen in Server Components and Server Actions. The browser never calls the API.

Two things follow from that, both deliberate:

- **The Clerk session token never enters the browser bundle.** `lib/api.ts` starts with
  `import "server-only"`, so importing it from a Client Component is a build error rather than a
  runtime leak.
- **CORS never applies.** The request is Node → FastAPI, not browser → FastAPI. The API's
  `BACKEND_CORS_ORIGINS` setting is therefore currently unused by this app; it stays configured for
  any future direct browser call.

### The base URL is not the `NEXT_PUBLIC_` one

```ts
process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
```

`NEXT_PUBLIC_*` values are inlined into the browser bundle at build time. Inside docker-compose the
API is reachable as `http://api:8000`, not `localhost` — so a server-side call must be able to use a
server-only variable. The public one remains as a fallback for local `npm run dev`.

## 4. Server Actions verify auth themselves

Every action begins with `requireSignedIn()`. This is not belt-and-braces: Server Functions are
reachable by **direct POST**, not only through the UI that rendered them, so a check on the page
that rendered the form protects nothing. The Next docs call this out explicitly, and it is the one
frontend mistake here with a real security consequence.

## 5. Errors are state, not exceptions

`createWatcherAction` catches `ApiError` and returns `{ error }` rather than throwing.

Hitting your plan limit is a **normal outcome**, not a fault — a 409 should render next to the form
with the API's own message ("Your free plan allows 1 watcher; you already have 1"), not blow up into
an error boundary. Non-API errors still throw, because those *are* faults.

The dashboard applies the same idea at page level: `loadDashboard` returns its failure so the page
can render a diagnostic card naming the likely cause. A backend that is down or missing
`CLERK_SECRET_KEY` is the most likely thing to break in local development, and a bare error boundary
tells the reader nothing about which.

## 6. Tier limits are not duplicated client-side

The form is always enabled, even at the watcher cap. The 409 from the API is what explains the
limit.

This is on purpose: `GET /me` returns `watchers_limit` and `subreddits_limit` precisely so the tier
table has one home, on the server. Re-implementing "is this user allowed to create another" in the
browser would mean two sources of truth that can disagree — and the client one is the one that can
be bypassed anyway.

## 7. Direction is a form field

The create form asks "I want to find people who are ⦿ requesting / ○ offering" rather than inferring
it from the description. Embeddings do not reliably encode which side of a transaction a post is
on — that finding is what motivated the whole direction axis in `docs/matcher/`. Asking the user
directly is the cheapest and most reliable signal available.

## 8. "Preparing…" is a real state

A watcher with `embedded_at === null` shows a **Preparing…** badge. Until the embedding worker has
processed it, the matcher skips it (it requires a non-NULL `intent_embedding`), so the watcher
genuinely is not doing anything yet. Editing a watcher's intent text puts it back into this state.

## 9. Known gaps

- **No editing.** The API supports `PATCH` of name, intent, subreddits and direction; the UI only
  exposes status (pause/resume) and delete.
- **No match feed.** There is no API endpoint for it yet, so confirmed matches are invisible in the
  UI. This is the biggest missing piece of the product loop.
- **No notification settings**, because there is no notification worker.
- **No optimistic UI.** Pause and delete wait for the round trip. Fine at this list size.
- **`useTransition` error handling is coarse** — `watcher-card.tsx` shows "That didn't work" without
  distinguishing causes. The detail is server-side in the action's logs.
- **No frontend tests.** Still no test framework in `/frontend`; flagged since the scaffold.
- **The empty state cannot distinguish "no watchers" from "all deleted"**, which is fine now but
  worth revisiting if onboarding gets more guided.
