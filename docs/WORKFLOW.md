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
    API->>Pipeline: embed intent_text, store watcher
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
    participant E as Embedding Worker
    participant DB as Postgres+pgvector
    participant M as Matcher
    participant L as LLM Verifier
    participant N as Notification Worker

    loop poll cycle
        I->>R: fetch new posts (subreddits from active watchers)
        I->>I: dedupe against seen post IDs
        I->>Q: enqueue new posts
        I->>I: emit heartbeat (uptime monitoring)
    end
    Q->>E: consume post
    E->>E: generate embedding (title+body)
    E->>DB: store post + embedding
    DB->>M: trigger match check
    M->>DB: similarity search vs active watchers (same subreddit)
    alt candidate above threshold
        M->>L: verify intent (needs vs offers)
        alt confirmed match
            L->>DB: write match row
            L->>N: enqueue notification
            N->>N: send via user's configured channels
            N->>DB: record delivery status
        else rejected by LLM
            L->>DB: discard (no match)
        end
    else below threshold
        M->>M: no action
    end
```
