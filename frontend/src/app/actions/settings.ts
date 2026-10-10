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
  // A success note worth showing (e.g. "Test message sent").
  message?: string;
  // A one-time link the user must open (Telegram connect).
  url?: string;
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

// Run an API call for a channel action, turning an API error into form state.
async function runChannelAction(
  call: () => Promise<unknown>,
  message?: string,
): Promise<ActionState> {
  try {
    await call();
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message };
    }
    throw error;
  }
  refresh();
  return { error: null, ok: true, message };
}

// Connect (or replace) Slack with a pasted incoming-webhook URL. The API sends a test message
// before saving, so a bad URL comes back here as an error instead of being stored.
export async function connectSlackAction(
  _previous: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireSignedIn();

  const webhookUrl = String(formData.get("webhook_url") ?? "").trim();
  if (!webhookUrl) {
    return { error: "Paste your Slack webhook URL." };
  }

  return runChannelAction(
    () =>
      apiFetch<Settings>("/settings/channels/slack", {
        method: "PUT",
        body: JSON.stringify({ webhook_url: webhookUrl }),
      }),
    "Slack connected. A test message was posted.",
  );
}

// Channels the generic actions below may touch. Validated server-side because a Server Function
// can be called directly with any form body, and this value ends up in an API path.
const MANAGEABLE_CHANNELS = ["slack", "telegram"];

function channelFrom(formData: FormData): string | null {
  const channel = String(formData.get("channel_type") ?? "");
  return MANAGEABLE_CHANNELS.includes(channel) ? channel : null;
}

// Switch a channel's alerts on or off without disconnecting it.
export async function setChannelEnabledAction(
  _previous: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireSignedIn();
  const channel = channelFrom(formData);
  if (!channel) return { error: "Unknown channel." };

  return runChannelAction(() =>
    apiFetch<Settings>(`/settings/channels/${channel}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: formData.get("enabled") === "true" }),
    }),
  );
}

// Post a sample notification to a connected channel.
export async function testChannelAction(
  _previous: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireSignedIn();
  const channel = channelFrom(formData);
  if (!channel) return { error: "Unknown channel." };

  return runChannelAction(
    () => apiFetch<void>(`/settings/channels/${channel}/test`, { method: "POST" }),
    "Test message sent.",
  );
}

// Forget a channel's saved connection entirely.
export async function disconnectChannelAction(
  _previous: ActionState,
  formData: FormData,
): Promise<ActionState> {
  await requireSignedIn();
  const channel = channelFrom(formData);
  if (!channel) return { error: "Unknown channel." };

  return runChannelAction(() =>
    apiFetch<void>(`/settings/channels/${channel}`, { method: "DELETE" }),
  );
}

// Get a one-time link that connects a Telegram chat. The connection completes in Telegram, not
// here: the user opens the link, presses Start, and the bot tells our API.
export async function createTelegramLinkAction(): Promise<ActionState> {
  await requireSignedIn();

  try {
    const link = await apiFetch<{ url: string; expires_in_minutes: number }>(
      "/settings/channels/telegram/link",
      { method: "POST" },
    );
    refresh();
    return {
      error: null,
      ok: true,
      url: link.url,
      message: `Link valid for ${link.expires_in_minutes} minutes.`,
    };
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message };
    }
    throw error;
  }
}
