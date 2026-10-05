"use server";

import { refresh } from "next/cache";
import { auth } from "@clerk/nextjs/server";

import { ApiError, apiFetch } from "@/lib/api";
import type { AdminUser } from "@/lib/types";

// Server Functions are reachable by direct POST, not only through our own UI, so every one of
// them re-checks auth rather than trusting the page that rendered the control. Whether the caller
// is actually a superadmin is enforced by the API's `require_superadmin` dependency — a non-admin
// hitting these just gets the same 403 back that curl would.
async function requireSignedIn(): Promise<void> {
  const { isAuthenticated } = await auth();
  if (!isAuthenticated) {
    throw new Error("Not signed in");
  }
}

export interface ActionState {
  error: string | null;
}

export async function updateUserPlanAction(userId: string, plan: string): Promise<ActionState> {
  await requireSignedIn();

  try {
    await apiFetch<AdminUser>(`/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ plan }),
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  refresh();
  return { error: null };
}

export async function setUserActiveAction(
  userId: string,
  isActive: boolean,
): Promise<ActionState> {
  await requireSignedIn();

  try {
    await apiFetch<AdminUser>(`/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  refresh();
  return { error: null };
}

// Deliberately doesn't call `refresh()` — unlike the actions above, the caller might be the user's
// own detail page, which has nothing left to refresh back to once the row is gone. The list page
// and the detail page each decide what to do next (re-render in place vs. navigate away).
export async function deleteUserAction(userId: string): Promise<ActionState> {
  await requireSignedIn();

  try {
    await apiFetch<void>(`/admin/users/${userId}`, { method: "DELETE" });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  return { error: null };
}
