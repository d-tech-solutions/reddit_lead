// Mirrors the Pydantic schemas in backend/app/schemas/. Kept hand-written rather than generated:
// the surface is small, and a generator would be one more build step to keep working.

export type WatcherDirection = "requesting" | "offering";
export type WatcherStatus = "active" | "paused";

export interface Watcher {
  id: string;
  name: string;
  intent_text: string;
  subreddits: string[];
  direction: WatcherDirection;
  status: WatcherStatus;
  created_at: string;
  // Null until the embedding worker has processed it — the UI shows "preparing" on that.
  embedded_at: string | null;
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
    created_at: string;
  };
  usage: Usage;
  // Confirmed matches not yet opened. Comes back with /me so the nav badge costs no extra request.
  unread_matches: number;
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
