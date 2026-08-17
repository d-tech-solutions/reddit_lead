# Auth & Watcher CRUD

Code-level walkthrough of the user-facing API's first real surface. Companion to [[ARCHITECTURE]] §3
and [[PRD]] §6 (tiers). This document describes what the code *currently does* — divergences from
the architecture doc are called out explicitly.

**What it does, in one sentence**: turns a Clerk session token into an account row, and lets that
account create and manage the watchers the pipeline runs on.

## 1. Files involved

| File | Purpose |
|---|---|
| [`backend/app/api/deps.py`](../../backend/app/api/deps.py) | Token extraction, Clerk verification, and the just-in-time account row. |
| [`backend/app/api/v1/endpoints/watchers.py`](../../backend/app/api/v1/endpoints/watchers.py) | The five CRUD endpoints. |
| [`backend/app/api/v1/endpoints/users.py`](../../backend/app/api/v1/endpoints/users.py) | `GET /me` — account plus usage against the plan. |
| [`backend/app/schemas/watcher.py`](../../backend/app/schemas/watcher.py) | Request/response shapes and the subreddit normaliser. |
| [`backend/app/services/limits.py`](../../backend/app/services/limits.py) | Tier enforcement, kept out of the endpoints so the arithmetic is testable without HTTP. |
| [`backend/app/core/constants.py`](../../backend/app/core/constants.py) | `TIER_LIMITS` from [[PRD]] §6, plus the direction/status vocabularies. |
| [`backend/app/models/user.py`](../../backend/app/models/user.py) | The `users` table. |
| [`backend/app/main.py`](../../backend/app/main.py) | Lifespan that holds the Arq pool for enqueueing embed jobs. |
| [`backend/alembic/versions/d4a9c2e71f38_add_users_and_watcher_owner.py`](../../backend/alembic/versions/d4a9c2e71f38_add_users_and_watcher_owner.py) | Creates `users`, adds `watchers.user_id`. **Deletes ownerless watchers** — see §5. |

## 2. Endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/me` | Account + usage. Creates the account row on first call. |
| `GET` | `/api/v1/watchers` | Caller's watchers, newest first. |
| `POST` | `/api/v1/watchers` | 201, or 409 when it would breach a plan limit. |
| `GET` | `/api/v1/watchers/{id}` | 404 for someone else's — see §4. |
| `PATCH` | `/api/v1/watchers/{id}` | Partial. Clears the vector if the intent changed. |
| `DELETE` | `/api/v1/watchers/{id}` | 204. Cascades the watcher's `matches` rows. |

## 3. Auth

### 3.1 Verification

`get_current_user` extracts the bearer token, verifies it with Clerk's `verify_token_async`
(RS256 against Clerk's JWKS, expiry enforced), then resolves it to a `User`.

Three responses worth knowing:

- **401** for a missing, malformed, or invalid token, always with `WWW-Authenticate: Bearer` so a
  browser client knows to re-authenticate. The *reason* for a verification failure is logged, never
  returned — telling a caller which part of their token failed helps whoever is probing the endpoint.
- **500** when `CLERK_SECRET_KEY` is unset, with a message naming the file to set it in. That is our
  misconfiguration, not the caller's bad credentials, and returning 401 would send people hunting
  for a problem with their token.
- **401** for a token that verifies but carries no `sub` claim — it verified, but it is not an
  identity.

`CLERK_AUTHORIZED_PARTIES` maps to Clerk's `azp` check. **Leaving it empty skips that check**, which
means a token minted for a *different* Clerk application would authenticate here. Acceptable locally,
not in production; the compose file defaults it to `http://localhost:3000`.

### 3.2 The account row is created just-in-time

There is no Clerk webhook. On the first authenticated request, if no row matches the `sub` claim,
one is inserted. Two requests from a brand-new user can race, so a unique-violation on insert is
caught and re-read rather than surfacing as a 500.

**What this defers, precisely.** Without a `user.deleted` webhook, deleting a Clerk account leaves
the `users` row behind, its watchers stay `active`, and **the ingestion worker keeps polling their
subreddits while the embedding worker keeps spending on the results.** That is a money leak, not
just stale data. Acceptable at zero users; it should not ship to production. Tracked in
[[PROGRESS]].

Email is refreshed opportunistically on each request, since without the webhook that is the only
moment we learn it changed. Which claim carries it depends on the Clerk token template, so
`email_from_claims` checks the three usual spellings rather than assuming one.

## 4. Watcher CRUD

### 4.1 Ownership is a 404, not a 403

`_get_owned_watcher` filters on `user_id` in the same query that loads by id, and raises 404 when
nothing comes back. A 403 would confirm that the id exists, which lets someone enumerate other
users' watchers. Tested for `GET`, `PATCH`, and `DELETE`.

### 4.2 Subreddit normalisation is load-bearing

`normalise_subreddit` strips `r/` and lowercases. This is not cosmetic. The ingestion worker builds
its poll list from these strings, and the matcher does an exact-string
`Watcher.subreddits.any(post.subreddit)`. If one watcher stored `ForHire` and another `forhire`:

- the ingestion worker would poll the same subreddit **twice**, and
- posts stored under one spelling would **never match** the watcher using the other.

Duplicates within a single watcher are dropped, preserving the order the user typed.

### 4.3 Intent length has a floor

`MIN_INTENT_CHARS = 15`. A three-word intent produces an embedding that sits near everything, so the
matcher would hand the verifier a stream of noise. Rejecting it at the edge is cheaper than
discovering it in the verifier's bill.

### 4.4 Editing the intent clears the vector

```python
watcher.intent_text = payload.intent_text
watcher.intent_embedding = None
watcher.embedded_at = None
```

Enqueueing a re-embed *alone* would leave a window where the matcher compares posts against the
**old** wording. Clearing the vector in the same transaction closes it: the matcher only considers
watchers with a non-NULL embedding, so this one is skipped until the embedding worker catches up —
and the embedding worker's backfill sweep finds it even if the enqueue fails.

This makes `embed_watcher(force=True)` belt-and-braces rather than the mechanism. Renaming a watcher
or changing its subreddits does **not** clear the vector — only `intent_text` feeds it, and
re-embedding on a rename would be spend for nothing. Both cases are tested, including re-sending an
unchanged intent.

### 4.5 Tier limits

From [[PRD]] §6, held in `TIER_LIMITS`:

| Plan | Watchers | Subreddits (pool) |
|---|---|---|
| free | 1 | 3 |
| standard | 3 | 10 |
| premium | 10 | 50 |
| enterprise | unlimited | unlimited |

Three details:

- **Subreddits are a pool shared across watchers**, counted as the **sum of list lengths** — PRD's own
  example spreads 10 as 3/3/4. Note the tension: the ingestion worker polls the *distinct union*, so
  two watchers both listing `r/forhire` cost one poll but consume two units of quota. Sum is the
  stricter reading and matches the written spec; flagged as an open product decision in [[PROGRESS]].
- **An edit is not a create.** `current_usage(exclude_watcher_id=...)` leaves the row being edited
  out of the count, so a user at their watcher cap can still edit what they have. Without that
  exclusion every edit would compare against a total that still included the row's old values.
- **Unknown plans fail closed** to the free tier. A typo in a plan string must not silently grant
  unlimited watchers.

The 409 message names the limit *and* current usage — "limit exceeded" alone forces the user to go
and count their own watchers.

### 4.6 The embed hand-off

`main.py`'s lifespan holds one Arq pool on `app.state.redis`. Create and intent-edit enqueue
`embed_watcher`. A missing pool or a failed enqueue is logged and swallowed, matching the other two
queue hand-offs: the API's job is serving requests, and the embedding worker's sweep recovers any
watcher left without a vector. Refusing to boot because a background queue is down would be the
worse trade.

## 5. Migration note — this one deletes data

`watchers.user_id` is `NOT NULL`, and watchers created before this migration have no owner to
assign. There is no correct value to invent, so the upgrade runs `DELETE FROM watchers`, taking
their `matches` rows with them via the existing cascade.

At the time it was written that meant **one seeded development watcher**. On any database with real
watchers this migration is destructive and would need a different strategy.

## 6. Testing

199 tests, split by what they need:

- **No services** (`pytest`): limit arithmetic, subreddit normalisation, schema validation, token
  extraction, and Clerk verification with `verify_token_async` monkeypatched. 175 tests.
- **Real Postgres** (`pytest -m db`): the endpoints. 24 tests, marked `db` and **skipped
  automatically** when Postgres is unreachable, so a plain `pytest` still passes with nothing
  running.

pgvector, `ARRAY`, and UUID rule out SQLite, and the FK cascades and tier queries are exactly what is
worth testing — so DB-backed tests earn their keep. Each runs inside a transaction that is rolled
back at teardown, so they are safe against a shared development database and order-independent. The
availability probe is memoised per session: probing an unreachable host per test turned a 4-second
suite into a 100-second one.

`auth_client` overrides both `get_db` (so endpoint writes land in the test transaction) and
`get_current_user` (so no real Clerk token is needed). Verification itself is covered separately.

## 7. Known gaps

- **No Clerk webhook** — see §3.2 for the cost. This is the most important gap here.
- **Nothing sets `plan` except the default.** Every account is `free` until Stripe lands; there is no
  admin path to change it.
- **No `notification_channels` or `subscriptions` tables.** Both are in [[ARCHITECTURE]] §4 and both
  belong to later milestones.
- **No match feed endpoint.** Confirmed matches are queryable in `matches` but no API exposes them.
- **Email may be absent.** The column is nullable because session tokens do not always carry the
  claim; the notification worker will need a fallback (a Clerk API lookup, or the webhook).
- **`GET /watchers` is unpaginated.** Fine at a 10-watcher cap; revisit if Enterprise arrives.
- **The API does not verify that `CLERK_AUTHORIZED_PARTIES` is set in production.** It is only a
  default in compose, not an enforced invariant.
