"use server";

import { auth } from "@clerk/nextjs/server";

import { apiFetch } from "@/lib/api";
import type { PostPage } from "@/lib/types";

// Server Functions are reachable by direct POST, not only through our own UI, so every one of them
// re-checks auth rather than trusting the page that rendered the button.
async function requireSignedIn(): Promise<void> {
  const { isAuthenticated } = await auth();
  if (!isAuthenticated) {
    throw new Error("Not signed in");
  }
}

// Fetch the next page of the posts feed, keeping whatever subreddit filter is active.
export async function loadMorePostsAction(
  cursor: string,
  subreddit: string | null,
): Promise<PostPage> {
  await requireSignedIn();

  const params = new URLSearchParams({ cursor });
  if (subreddit) params.set("subreddit", subreddit);
  return apiFetch<PostPage>(`/posts?${params.toString()}`);
}
