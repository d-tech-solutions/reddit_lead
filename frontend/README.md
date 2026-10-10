# PostPing frontend

Next.js (App Router) app. See `/docs` at the repo root for product/architecture context.

## Dev setup

```bash
npm install
cp .env.example .env.local   # fill in Clerk keys, adjust NEXT_PUBLIC_API_BASE_URL if needed
npm run dev
```

- App: http://localhost:3000
- `/sign-in`, `/sign-up` — Clerk auth
- `/dashboard` — protected placeholder (redirects to `/sign-in` if unauthenticated)

Requires a Clerk application (publishable + secret key) — see `.env.example`. The backend
(`/backend`) should be running on `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`)
for API calls to succeed once they're wired up.

## Lint

```bash
npm run lint
```

## Build

```bash
npm run build
npm run start
```

## Docker

```bash
docker build -t postping-frontend .
docker run --env-file .env.local -p 3000:3000 postping-frontend
```

## Notes

- Next.js 16: uses `proxy.ts` (not `middleware.ts` — renamed upstream) to wire
  `clerkMiddleware()`. Route protection is done per-page via `auth()` /
  `redirectToSignIn()`, not middleware-level matchers (Clerk's `createRouteMatcher` is
  deprecated as of this Next/Clerk version).
- No test framework wired yet — deferred until there's real UI to test.
