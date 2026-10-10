// Mirrors the Pydantic schemas in backend/app/schemas/. Kept hand-written rather than generated:
// the surface is small, and a generator would be one more build step to keep working.

export type WatcherStatus = "active" | "paused";

export interface Watcher {
  id: string;
  name: string;
  intent_text: string;
  subreddits: string[];
  status: WatcherStatus;
  created_at: string;
}

export interface Usage {
  watchers_used: number;
  // Null means unbounded (the enterprise tier).
  watchers_limit: number | null;
  subreddits_used: number;
  subreddits_limit: number | null;
}

export interface Me {
  user: {
    id: string;
    email: string | null;
    plan: string;
    // Gates the Admin/Posts nav items and the /admin routes client-side. The API enforces this
    // independently — see `require_superadmin` — this is just for what the UI shows.
    is_superadmin: boolean;
    created_at: string;
  };
  usage: Usage;
  // Confirmed matches not yet opened. Comes back with /me so the nav badge costs no extra request.
  unread_matches: number;
}

// One row of the superadmin user list.
export interface AdminUser {
  id: string;
  email: string | null;
  plan: string;
  is_active: boolean;
  is_superadmin: boolean;
  created_at: string;
  watcher_count: number;
}

export interface AdminUserDetail extends AdminUser {
  watchers: Watcher[];
}

export interface MatchPost {
  reddit_post_id: string;
  subreddit: string;
  title: string;
  author: string | null;
  permalink: string;
  // Null when the fetch mode did not supply one — the RSS source sometimes omits it.
  posted_at: string | null;
}

export interface Match {
  id: string;
  // When the verifier confirmed it. The feed's sort key, and what the card shows as its age.
  matched_at: string;
  read_at: string | null;
  // The verifier's own sentence explaining why this post matched.
  reason: string | null;
  watcher: { id: string; name: string };
  post: MatchPost;
}

export interface MatchPage {
  items: Match[];
  // Null on the last page. Pass it back as `?cursor=` to get the next one.
  next_cursor: string | null;
  unread: number;
}

// A raw ingested post — unlike `MatchPost`, this carries the body, since the posts feed has
// nowhere else to show it.
export interface Post {
  id: string;
  reddit_post_id: string;
  subreddit: string;
  title: string;
  body: string;
  author: string | null;
  permalink: string;
  // Null when the fetch mode did not supply one — the RSS source sometimes omits it.
  posted_at: string | null;
  // When the ingestion worker stored this row, as opposed to when Reddit says it was posted.
  fetched_at: string;
}

export interface PostPage {
  items: Post[];
  // Null on the last page. Pass it back as `?cursor=` to get the next one.
  next_cursor: string | null;
  // Every subreddit the caller can filter to — the union across their watchers, not just the
  // ones with a post on this page.
  subreddits: string[];
}

export interface NotificationChannel {
  channel_type: string;
  enabled: boolean;
  verified: boolean;
  // A connect link was issued and is still waiting for the user to open it (Telegram).
  link_pending: boolean;
}

export interface Settings {
  // The Clerk-synced login address — shown as the notification_email override's fallback.
  account_email: string | null;
  notification_email: string | null;
  channels: NotificationChannel[];
}

// One row of the pricing table, straight from `core.constants.TIER_LIMITS` — the same numbers
// the API enforces, so the pricing UI can't drift from what a plan actually allows.
export interface Plan {
  id: string;
  price_cents: number;
  // Null means unbounded (no tier currently is, but the API leaves the door open).
  max_watchers: number | null;
  max_subreddits: number | null;
}

export interface Billing {
  plan: string;
  status: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}

// Mirrors backend/app/schemas/analytics.py. Rates are 0–1, or null when nothing was decided.
export interface VerdictTotals {
  confirmed: number;
  rejected: number;
  pending: number;
  pass_rate: number | null;
}

export interface DailyCount {
  // ISO date (YYYY-MM-DD), UTC.
  day: string;
  confirmed: number;
}

export interface SubredditStat {
  subreddit: string;
  confirmed: number;
  reviewed: number;
  pass_rate: number | null;
}

export interface WatcherStat {
  id: string;
  name: string;
  status: WatcherStatus;
  confirmed: number;
  reviewed: number;
  pass_rate: number | null;
  last_match_at: string | null;
}

export interface Analytics {
  days: number;
  totals: VerdictTotals;
  daily: DailyCount[];
  top_subreddits: SubredditStat[];
  watchers: WatcherStat[];
}
