# Billing

Stripe Checkout + Billing Portal for the three paid tiers (`standard`, `premium`, `enterprise`).
`free` has no Stripe object at all. See [PRD §6](../PRD.md) for the pricing table this enforces.

Two places hold plan state, on purpose:

- `users.plan` ([backend/app/models/user.py](../../backend/app/models/user.py)) — the fast,
  always-current field every other query reads: `limits_for_plan()` in
  [core/constants.py](../../backend/app/core/constants.py), `enforce_limits()` in
  [services/limits.py](../../backend/app/services/limits.py), and the `/me` endpoint.
- `subscriptions` ([backend/app/models/subscription.py](../../backend/app/models/subscription.py))
  — at most one row per user, holding the Stripe-specific detail (customer/subscription ids,
  renewal date, cancellation flag) that only the billing endpoints and the settings page need.

[services/billing.py](../../backend/app/services/billing.py) is where both are kept in sync.

## Checkout and portal

`create_checkout_session()` and `create_portal_session()` build a Stripe-hosted URL and hand it
back to the caller — the frontend redirects to it directly (see
[frontend/src/app/actions/billing.ts](../../frontend/src/app/actions/billing.ts)). Neither the
card number nor any Stripe secret ever reaches our frontend code.

Checkout reuses an existing Stripe customer if the user has subscribed before (read off their
`subscriptions` row), so a re-subscribe or a plan change doesn't create a second customer object
for the same person.

Every Checkout Session is created with two places carrying the same information, deliberately
redundant:

- `client_reference_id` / `metadata.plan` on the **Checkout Session** — read by the
  `checkout.session.completed` handler, since that event's object is the session itself.
- `subscription_data.metadata.user_id` — copied onto the **Subscription** object Stripe creates,
  so it's still there on every later `customer.subscription.*` event for that subscription's
  lifetime, including ones triggered by the customer using the Billing Portal directly (which
  Checkout has nothing to do with).

## Webhook (`POST /billing/webhook`)

The one endpoint with no `get_current_user` dependency — Stripe calls it directly, authenticated
by `verify_webhook_signature()` checking the `Stripe-Signature` header against
`STRIPE_WEBHOOK_SECRET` instead of a bearer token. An invalid signature is a 400; an unrecognised
event *type* is accepted (200) and ignored, since Stripe expects every event type to get a 200
eventually, not just the ones we act on (`_HANDLERS` in services/billing.py).

Three event types are handled:

- **`checkout.session.completed`** — first sight of a new subscription. Reads `plan` off the
  session's own metadata, upserts the `subscriptions` row, sets `users.plan`.
  `current_period_end` is left `None` here; the `customer.subscription.updated` event Stripe fires
  moments later fills it in.
- **`customer.subscription.updated`** — fired on renewal, and on any plan change (including one
  made through the Billing Portal, not our Checkout flow). The plan is re-derived from the
  subscription's **current price id** (`_plan_for_price_id()`), not from metadata — metadata can
  go stale after a portal-driven price swap, but the price id is always authoritative.
- **`customer.subscription.deleted`** — full cancellation. Falls back to `DEFAULT_PLAN` ("free")
  on `users.plan` and marks the `subscriptions` row `status="canceled"`. The row itself is kept as
  a record, not deleted.

All three identify the user via `metadata.user_id`, never by looking up `stripe_customer_id` in
our own table — that lookup would fail for the very first event on a fresh signup and adds a
dependency the metadata already avoids.

## Downgrade / cancellation behavior

Nothing here touches a user's existing watchers or subreddits. `enforce_limits()`
([services/limits.py](../../backend/app/services/limits.py)) already reads `users.plan` on every
create/edit, so the moment `users.plan` drops to `free`, the *existing* watchers keep running
exactly as configured — the user just can't create a new one or grow a subreddit list until they're
back under the new plan's limit. No pause-on-downgrade logic exists or is planned; see the PRD
pricing section for why this was chosen over auto-pausing the newest-over-the-limit watchers.

## Enterprise is self-serve

Unlike the original architecture sketch, Enterprise is a real, capped Stripe price
(`STRIPE_PRICE_ENTERPRISE`, 25 watchers / 150 subreddits) rather than "contact sales" — an
uncapped tier at a fixed monthly price would let a single account drive unbounded ingestion/LLM
cost (PRD §8's cost-scaling risk). `PAID_PLANS` in core/constants.py is every tier except `free`.

## Local dev

Stripe needs a reachable webhook URL. Locally, run the Stripe CLI alongside `docker compose up`:

```
stripe listen --forward-to localhost:8000/api/v1/billing/webhook
```

It prints a temporary signing secret — put it in `STRIPE_WEBHOOK_SECRET` in `backend/.env` (or the
root `.env` for docker compose) and restart the `api` service. `STRIPE_PRICE_STANDARD` /
`_PREMIUM` / `_ENTERPRISE` are the three recurring monthly Price ids from a test-mode Stripe
Product; without them, `/billing/checkout` returns a 400 rather than silently failing.
