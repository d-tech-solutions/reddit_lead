"use server";

import { auth } from "@clerk/nextjs/server";

import { apiFetch } from "@/lib/api";
import type { Match, MatchPage } from "@/lib/types";

// Server Functions are reachable by direct POST, not only through our own UI, so every one of them
// re-checks auth rather than trusting the page that rendered the button.
async function requireSignedIn(): Promise<void> {
  const { isAuthenticated } = await auth();
  if (!isAuthenticated) {
    throw new Error("Not signed in");
  }
}

// Fetch the next page of the feed.
//
// A read behind a Server Action rather than a browser fetch: the Clerk token stays on the server,
// which is the same reason every other call in this app goes through `apiFetch`. Passing a cursor
// for someone else's feed gains nothing — the API scopes every query to the caller's own watchers.
export async function loadMoreMatchesAction(cursor: string): Promise<MatchPage> {
  await requireSignedIn();

  const query = new URLSearchParams({ cursor });
  return apiFetch<MatchPage>(`/matches?${query.toString()}`);
}

// Mark one match as read. Returns the updated match so the caller can render from the response.
//
// No `refresh()`: the feed keeps its loaded pages in client state, and re-rendering the route
// would throw away everything the user had paged in. The badge is updated locally instead, and
// any other route re-reads it on navigation (dynamic pages have a zero client-cache stale time).
export async function markMatchReadAction(id: string): Promise<Match> {
  await requireSignedIn();

  return apiFetch<Match>(`/matches/${id}/read`, { method: "POST" });
}

// Clear every unread match at once.
export async function markAllMatchesReadAction(): Promise<void> {
  await requireSignedIn();

  await apiFetch<{ updated: number; unread: number }>("/matches/read-all", { method: "POST" });
}
