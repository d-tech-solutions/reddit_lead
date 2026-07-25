# Features

See [[PRD]] for the product rationale behind these decisions. Features are grouped by phase.
Phase 1 is the MVP — nothing in Phase 2/3 should block Phase 1 shipping.

## Phase 1 — MVP

### Account & auth
- Email/password or OAuth sign-up and login
- Basic account settings page
- Free vs Paid plan flag on the account (manual/Stripe-driven — see Billing below)

### Watchers
- Create a watcher: name, 1+ subreddits, plain-language intent description
- Edit / pause / delete a watcher
- Enforce per-plan limits (watcher count, subreddits per watcher)
- List view of all watchers with status (active/paused, last match time)

### Ingestion & matching engine
- Poll selected subreddits for new posts via Reddit's official API (OAuth)
- Deduplicate posts already processed
- Embed new posts
- Embed watcher intent descriptions (on create/edit)
- Vector similarity search: new post embedding vs. active watcher embeddings
- LLM verification pass on candidates above similarity threshold (needs-service vs.
  offers-service disambiguation — see [[PRD]] problem statement)
- On confirmed match: write to matches table, enqueue notification

### Dashboard (in-app inbox)
- Feed of matched posts per watcher (and combined "all matches" view)
- Each match shows: subreddit, post title/snippet, link to Reddit, matched watcher, timestamp
- Mark a match as read/unread

### Notifications
- Email notification per match (configurable: instant vs. digest — instant for MVP, digest is a
  fast follow)
- Telegram notification per match (user links their Telegram via bot deep link)
- Per-watcher notification channel toggle

### Billing (freemium)
- Stripe integration for upgrading Free → Paid
- Plan limits enforced server-side, not just in UI

### Ops basics
- Health check endpoint(s) for each worker stage
- Structured logging
- Error tracking wired in (Sentry) — see [[ARCHITECTURE]]

## Phase 2 — Quality & growth

- **Feedback loop**: thumbs up/down on a match, feeding back into per-watcher match threshold
  tuning (flagged as roadmap, not MVP, per PRD decision)
- Digest notification mode (hourly/daily summary instead of instant)
- Discord webhook + generic outgoing webhook channels
- Watcher-level match threshold control (advanced users can tune sensitivity)
- Search/filter within the match dashboard
- Usage analytics for the user (matches/week, click-through to Reddit)

## Phase 3 — Scale & expansion

- Self-hosted embedding model (cost optimization at higher ingestion volume)
- Auto-suggest relevant subreddits when creating a watcher (still requires user confirmation —
  full auto-discovery without confirmation is explicitly out of scope per [[PRD]])
- Team/agency accounts (multiple seats sharing watchers)
- Additional intent categories beyond "needs a service" (e.g. hiring posts, deal alerts) —
  validate demand before building
- Multi-region deployment if latency/availability requires it

## Explicitly not planned

- Auto-replying to Reddit posts on the user's behalf
- Non-Reddit sources
- Native mobile app
