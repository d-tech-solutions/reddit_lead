# Product Requirements Document

**Product name:** PostPing
**Status:** Draft v1
**Last updated:** 2026-07-25

## 1. Problem statement

People who offer a service (freelancers, agencies, consultants) or watch for a specific kind of
ask on Reddit currently have to manually scroll relevant subreddits all day to catch posts where
someone expresses a need — e.g. "I need a WordPress site built." By the time they see it, several
competitors may have already replied. Reddit's own search/keyword alerts are keyword-based, not
intent-based, so they produce a lot of noise (a keyword match on "WordPress" also matches people
*offering* WordPress services, tutorials, complaints, etc.).

## 2. Product vision

A SaaS app where a user describes, in plain language, the kind of request they want to be
notified about (scoped to specific subreddits), and the app continuously watches those
subreddits, understands the *intent* of each new post (not just keywords), and notifies the user
in near real time when a genuine match appears.

## 3. Target users

- Freelance web/software developers (the original motivating case: WordPress dev leads)
- Freelancers in other service categories (design, writing, marketing, video editing)
- Small agencies wanting a lead-gen channel from Reddit
- Later: anyone who wants intent-based alerts on Reddit beyond "needs a service" (job seekers
  watching for hiring posts, deal-hunters, recruiters, etc.) — not MVP scope, but the matching
  engine is generic enough to support it later.

## 4. Goals & success metrics

- **Precision over recall**: a small number of high-quality matches beats a firehose of loosely
  related posts. Target: user-perceived false-positive rate low enough that they don't disable
  notifications.
- **Speed**: notify within minutes of the post going live — being first to reply matters a lot in
  "for hire" style threads.
- **Activation**: a new user creates their first watcher and receives their first real match
  within their first session/day.
- Early success metric (pre-scale): number of active watchers × user-reported "this was a good
  match" rate. Formal analytics come later (see [[FEATURES]] feedback loop, post-MVP).

## 5. Non-goals (explicitly out of scope for now)

- Auto-discovering relevant subreddits for a user (MVP requires user to pick subreddits explicitly
  — see architecture decision in brainstorm).
- Posting/replying to Reddit on the user's behalf.
- Full analytics/BI dashboard on lead conversion.
- Mobile app (web-responsive dashboard only).
- Supporting platforms other than Reddit.

## 6. Pricing / tiers (Freemium)

All tiers get the same matching speed (near real-time polling) — see architecture decision. The
differentiator is **capacity and channels**, not latency.

| | Free | Standard | Premium | Enterprise |
|---|---|---|---|---|
| Watchers | 1 | 3 | 10 | Custom |
| Subreddits (total across watchers) | 3 | 10 | 50 | Custom |
| Notification channels | Email only | Email + Telegram | Email + Telegram | Custom |
| Match history / dashboard | Yes | Yes | Yes | Yes |
| Matching speed | Same across all tiers | Same across all tiers | Same across all tiers | Same across all tiers |
| Price | $0 | TBD | TBD | Contact sales |

Subreddit limits are a **total pool shared across a user's watchers**, not per-watcher (e.g. a
Standard user could put all 10 subreddits on one watcher, or spread them 3/3/4 across three
watchers). Standard/Premium dollar pricing is still open — flagged in [[PROGRESS]].

## 7. Core user flow (MVP)

1. User signs up (email/OAuth).
2. User creates a **watcher**: picks 1+ subreddits, writes a plain-language description of the
   intent they want to catch (e.g. "someone asking for a WordPress developer to build or fix
   their site").
3. System embeds the watcher's intent description and stores it.
4. System continuously ingests new posts from the selected subreddits, embeds them, and checks
   for similarity against active watchers; candidates go through an LLM intent-verification pass.
5. On a confirmed match: the post appears in the user's dashboard, and a notification is sent via
   their configured channel(s).
6. User clicks through to the Reddit post to respond.

Full sequence detail lives in [[WORKFLOW]].

## 8. Key risks / assumptions

- **Reddit API terms & rate limits**: must operate within Reddit's official API (OAuth, ~100 QPM
  class limits) — no scraping workarounds. This bounds how many subreddits/posts we can poll and
  is the reason watchers are scoped to specific subreddits rather than all of Reddit.
- **Embedding/LLM cost scales with ingestion volume**, not directly with paying users — a small
  number of watchers on high-traffic subreddits could still generate significant background cost.
  Needs cost monitoring from day one (see [[ARCHITECTURE]] monitoring section).
- **False positives erode trust fast** — the two-stage match (embedding retrieval + LLM
  verification) exists specifically to manage this; matching quality is the core product risk,
  not a nice-to-have.
- **Cold-start matching quality**: without the feedback loop (post-MVP), match thresholds are
  tuned manually/globally rather than per-watcher.

## 9. Related docs

- [[FEATURES]] — full feature breakdown by phase
- [[ARCHITECTURE]] — technical design, stack, data model, monitoring
- [[WORKFLOW]] — user and system sequence flows
- [[PROGRESS]] — current status and open decisions
