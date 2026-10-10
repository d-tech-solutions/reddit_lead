# Analytics dashboard

`GET /api/v1/analytics?days=30` (1–365) returns everything the `/analytics` page renders in one call.

- **Code**: `app/services/analytics.py` (queries), `app/schemas/analytics.py`,
  `app/api/v1/endpoints/analytics.py`. Frontend: `frontend/src/app/(app)/analytics/page.tsx`
  (Server Component; the 7/30/90-day picker is plain links to `?days=`).
- **Ownership**: every query joins `matches -> watchers` and filters on `watchers.user_id`, as in
  `services/matches.py`.
- **Definitions**: confirmed = `llm_verified IS TRUE`, rejected = `IS FALSE`, pending = `IS NULL`.
  `pass_rate = confirmed / (confirmed + rejected)`; pending is excluded, and the rate is null
  (shown as "—") when nothing has been decided.
- **Good vs bad is the AI verifier's verdict, not the user's.** There is no match-feedback column
  yet. When thumbs up/down lands, swap the totals and per-subreddit/per-watcher rates to use it.
- **Daily series** is bucketed by UTC day and zero-filled to `days` entries.
- **Watcher table** lists every owned watcher, including ones with no matches in the window
  (the window is in the outer-join condition, not `WHERE`).
- Charts are plain CSS bars — no chart dependency.
- Tests: `backend/tests/test_analytics_api.py` (DB-backed).
