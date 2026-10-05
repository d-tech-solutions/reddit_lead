"use server";

import { auth } from "@clerk/nextjs/server";

import { ApiError, apiFetch } from "@/lib/api";

// Server Functions are reachable by direct POST, not only through our own UI, so every one of
// them re-checks auth rather than trusting the page that rendered the form.
async function requireSignedIn(): Promise<void> {
  const { isAuthenticated } = await auth();
  if (!isAuthenticated) {
    throw new Error("Not signed in");
  }
}

export interface ActionState {
  error: string | null;
}

// Permanently deletes the caller's account: cancels billing, deletes the Clerk identity, and
// removes the local row (which cascades to watchers, matches, and notification channels).
//
// Called directly from a client `onClick`, not a `<form action>`, since the confirm dialog needs
// to sign the browser out afterwards — something only client-side Clerk can do.
export async function deleteAccountAction(): Promise<ActionState> {
  await requireSignedIn();

  try {
    await apiFetch<void>("/me", { method: "DELETE" });
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message };
    }
    throw error;
  }

  return { error: null };
}
