# Workflows

Companion to [[ARCHITECTURE]]. Two workflows: what the user experiences, and what the system does
in the background to make it happen.

## 1. User-facing workflow: onboarding to first match

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Next.js Frontend
    participant API as FastAPI
    participant Pipeline as Ingestion/Match Pipeline

    U->>FE: Sign up
    FE->>API: create account
    U->>FE: Create watcher (subreddits + intent text)
    FE->>API: POST /watchers
    API->>API: enforce plan limits (watcher/subreddit count)
    API->>Pipeline: store watcher
    Note over Pipeline: Pipeline now polls this watcher's subreddits
    U->>FE: Link Telegram (optional) / confirm email channel
    Pipeline-->>API: confirmed match found
    API-->>U: Email / Telegram notification
    U->>FE: Open dashboard, see match in inbox
    U->>FE: Click through to Reddit post to respond
```

Notes:
- Notification channel setup can happen before or after the first watcher is created; email
  defaults to the account email, Telegram requires an explicit link step (bot deep link).
- Free-tier users are capped at watcher/subreddit creation time — the UI should surface the limit
  before the API rejects the request, not just show a generic error.

## 2. System workflow: post ingestion to notification

```mermaid
sequenceDiagram
    participant R as Reddit API
    participant I as Ingestion Worker
    participant Q as Redis Queue
    participant DB as Postgres
    participant M as Matcher Worker
    participant L as LLM Verifier (GPT-4o-mini)
    participant N as Notification Worker

    loop poll cycle
        I->>R: fetch new posts (subreddits from active watchers)
        I->>I: dedupe against seen post IDs
        I->>DB: store post
        I->>Q: enqueue match job
        I->>I: emit heartbeat (uptime monitoring)
    end
    Q->>M: consume post
    M->>DB: find active watchers subscribed to this post's subreddit
    alt no watchers subscribed
        M->>M: no action
    else one or more watchers
        M->>L: batched verification call (post + all candidate watcher intents)
        L->>M: per-watcher verdict + reasoning
        loop each verdict
            M->>DB: one transaction: store outcome + delete the queued post
            alt confirmed match
                M->>N: enqueue notification
                N->>N: send via user's configured channels
                N->>DB: record delivery status
            end
        end
    end
```

Notes:
- One LLM call per post, not one per (post, watcher) pair — the call is batched across every
  active watcher subscribed to that post's subreddit, and returns a verdict per watcher.
- Only confirmed verdicts become `matches` rows (with the post copied to `matched_posts`).
  Rejected candidates are counted in `match_stats` and sampled into a 7-day `rejection_log`; the
  queued post is deleted either way, so `reddit_posts` only ever holds posts awaiting the LLM.
- A new watcher judges posts made at or after its creation; a one-off catch-up job judges the
  previous hour (fetched straight from Reddit) against that watcher alone.
- Large subreddits (many subscribed watchers) split into multiple batched calls rather than one
  unbounded call.
