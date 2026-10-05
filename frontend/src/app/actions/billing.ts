"use server";

import { redirect } from "next/navigation";
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

// Shared by checkout and portal: call the API for a Stripe-hosted URL, then redirect to it.
// `redirect()` throws, so it must run outside the try/catch — see Next's docs on redirect().
async function startStripeFlow(path: string, body?: unknown): Promise<ActionState> {
  await requireSignedIn();

  let url: string;
  try {
    const result = await apiFetch<{ url: string }>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
    url = result.url;
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message };
    }
    throw error;
  }

  redirect(url);
}

// Bound with a plan id via `.bind(null, plan)` so each pricing-card form can submit without a
// hidden field — see the "Passing additional arguments" pattern in Next's Server Actions guide.
// The trailing params exist only so the bound function still matches the two-argument shape
// `useActionState` calls it with; neither is read.
/* eslint-disable @typescript-eslint/no-unused-vars */
export async function startCheckoutAction(
  plan: "standard" | "premium" | "enterprise",
  _previous: ActionState,
  _formData: FormData,
): Promise<ActionState> {
  return startStripeFlow("/billing/checkout", { plan });
}

export async function openPortalAction(
  _previous: ActionState,
  _formData: FormData,
): Promise<ActionState> {
  return startStripeFlow("/billing/portal");
}
/* eslint-enable @typescript-eslint/no-unused-vars */
