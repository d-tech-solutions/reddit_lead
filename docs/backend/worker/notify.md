# Notify worker

Tells users about confirmed matches. Own Arq process: `arq app.workers.notify.WorkerSettings`
(compose service `worker-notify`).

## Flow

1. The matcher (`match_post`) confirms matches, then enqueues `notify_match(match_id)` for each
   (`enqueue_notifications` in `app/workers/match.py`). Job id `notify_match:<id>` dedupes.
2. `notify_match` loads match/post/watcher/user, skips if the match isn't confirmed, the watcher is
   paused or the user is inactive, then walks the user's channels that are **configured, enabled and
   verified**.
3. Each (match, channel) gets a `notification_deliveries` row (unique pair). `sent` / `failed` /
   `skipped` are terminal and never revisited, so retries and duplicate jobs can't double-send.
4. A cron sweep (`backfill`, every `NOTIFY_BACKFILL_INTERVAL_MINUTES`) re-runs `notify_match` for
   confirmed matches from the last `NOTIFY_BACKFILL_WINDOW_HOURS` that have `notified_at IS NULL` and
   no failed/skipped delivery. It covers failed enqueues and half-finished deliveries, and the window
   stops a newly connected channel from replaying old matches.

## Failure handling

Notifiers raise `TemporaryDeliveryError` (timeout, 429, 5xx) or `PermanentDeliveryError` (bad
credentials, revoked webhook, 4xx). Temporary: attempt is counted and the job raises `arq.Retry`
(30s, 60s, ...) until `NOTIFY_MAX_ATTEMPTS`, then the delivery is `failed`. Permanent: `failed`
immediately, and a non-email channel is flipped to `verified=false` so the UI can ask to reconnect.

## Channels

- **email** (built): Resend HTTP API via httpx. Address is `users.notification_email` or
  `users.email`. On by default; the `notification_channels` email row only exists once the user
  opens settings, so a missing row means "on". Without `RESEND_API_KEY` the notifier isn't
  registered and matches stay un-notified for the sweep. Resend's `onboarding@resend.dev` sender
  only delivers to the Resend account owner — a verified domain is needed for real users.
- **slack** (built): free on all plans. The user pastes an incoming-webhook URL on the
  Notifications page; `PUT /settings/channels/slack` sends a test message first and only saves on
  success. The URL is Fernet-encrypted (`NOTIFY_ENCRYPTION_KEY`) into
  `notification_channels.config["webhook_url_encrypted"]`, never returned by the API, and decrypted
  only at send time. Only `https://hooks.slack.com/(services|workflows)/...` URLs are accepted, since
  our server posts to whatever the user supplies (SSRF guard); redirects aren't followed. Post text
  is escaped so a Reddit title can't ping `<!channel>`. A dead webhook (404/403/410) or an
  undecryptable one marks the channel `verified=false` ("Needs reconnect" in the UI); reconnecting
  clears it. Missing key: the API answers 503 and the worker leaves deliveries pending.
  Other endpoints: `PATCH /settings/channels/{type}` (pause/resume), `DELETE` (disconnect, not
  allowed for email), `POST .../test` (sample message to the real destination).
- **telegram** (built): paid plans only (`channel_allowed` in `app/core/constants.py`, checked when
  creating a link, on "Send test", and again in the worker so a downgraded user stops receiving).
  Connecting happens in Telegram: `POST /settings/channels/telegram/link` creates a one-time token
  (stored as a SHA-256 hash with an expiry, `TELEGRAM_LINK_TTL_MINUTES`) and returns
  `https://t.me/<bot>?start=<token>`. When the user presses Start, Telegram calls
  `POST /api/v1/telegram/webhook` (`app/api/v1/endpoints/telegram.py`) with `/start <token>` and the
  chat id; `complete_link` swaps the token for `config["destination"]` and sets `verified=true`.
  The webhook is unauthenticated except for the `X-Telegram-Bot-Api-Secret-Token` header
  (`TELEGRAM_WEBHOOK_SECRET`, constant-time compared); it ignores group chats and always answers
  200 past the secret check so Telegram doesn't retry. Replacing a connected chat keeps the old one
  working until the new Start arrives. Bot-blocked (403) / chat-not-found (400) mark the channel
  `verified=false`; a 401 (our bot token is wrong) is treated as temporary so users' channels
  aren't flagged for our misconfiguration. Register the webhook with
  `python -m scripts.set_telegram_webhook https://<public-host>` (needs a tunnel locally).

Adding a channel = one module in `app/notifiers/` implementing `Notifier`, registered in
`build_notifiers`, with its destination stored in `notification_channels.config["destination"]`.
