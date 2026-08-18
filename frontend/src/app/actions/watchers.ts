"use server";

import { refresh } from "next/cache";
import { auth } from "@clerk/nextjs/server";

import { ApiError, apiFetch } from "@/lib/api";
import type { Watcher, WatcherStatus } from "@/lib/types";

// Server Functions are reachable by direct POST, not only through our own UI, so every one of
// them re-checks auth rather than trusting the page that rendered the form.
// (Next docs: "Always verify authentication and authorization inside every Server Function.")
async function requireSignedIn(): Promise<void> {
  const { isAuthenticated } = await auth();
  if (!isAuthenticated) {
    throw new Error("Not signed in");
  }
}

export interface ActionState {
  error: string | null;
  // Bumped on success so a client form can tell "worked" from "first render".
  ok?: boolean;
}

// Split a textarea of subreddits into a list. Accepts commas, spaces, or newlines, because people
// paste all three — the backend normalises the individual names (strips r/, lowercases).
function parseSubreddits(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((value) => value.trim())
    .filter(Boolean);
}

// Create a watcher from the dashboard form.
//
// Returns the error as state rather than throwing, so a plan-limit 409 renders next to the form
// instead of blowing up into an error boundary — hitting your tier limit is normal, not a fault.
export async function createWatcherAction(
  _previous: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireSignedIn();

  const payload = {
    name: String(formData.get("name") ?? "").trim(),
    intent_text: String(formData.get("intent_text") ?? "").trim(),
    subreddits: parseSubreddits(String(formData.get("subreddits") ?? "")),
  };

  try {
    await apiFetch<Watcher>("/watchers", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message };
    }
    throw error;
  }

  // Our data lives in FastAPI, not Next's data cache, so `refresh()` (which re-renders the route)
  // is the right tool here — `revalidateTag`/`revalidatePath` target caches we do not populate.
  refresh();
  return { error: null, ok: true };
}

// Pause or resume a watcher. A paused watcher contributes no subreddits to the ingestion worker,
// so this is how a user stops the pipeline spending on them without losing the configuration.
export async function setWatcherStatusAction(id: string, status: WatcherStatus): Promise<void> {
  await requireSignedIn();

  await apiFetch<Watcher>(`/watchers/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });

  refresh();
}

// Delete a watcher and everything matched against it.
export async function deleteWatcherAction(id: string): Promise<void> {
  await requireSignedIn();

  await apiFetch<void>(`/watchers/${id}`, { method: "DELETE" });

  refresh();
}
