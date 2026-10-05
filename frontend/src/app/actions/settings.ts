"use server";

import { refresh } from "next/cache";
import { auth } from "@clerk/nextjs/server";

import { ApiError, apiFetch } from "@/lib/api";
import type { Settings } from "@/lib/types";

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
  // Bumped on success so a client form can tell "worked" from "first render".
  ok?: boolean;
}

// Save the notification-email override and the email channel's enabled state.
//
// Returns the error as state rather than throwing, so a validation failure renders next to the
// form instead of blowing up into an error boundary.
export async function updateSettingsAction(
  _previous: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireSignedIn();

  const payload = {
    notification_email: String(formData.get("notification_email") ?? "").trim() || null,
    email_enabled: formData.get("email_enabled") === "on",
  };

  try {
    await apiFetch<Settings>("/settings", {
      method: "PATCH",
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
