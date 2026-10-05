import { auth } from "@clerk/nextjs/server";

import { AppSidebar } from "@/components/app-sidebar";
import { apiFetch } from "@/lib/api";
import type { Me } from "@/lib/types";

// Shared shell for every signed-in route: the sidebar plus whatever the page renders.
//
// Fetches `/me` once here rather than in each page, since every page under this group needs the
// plan/usage/unread numbers for the sidebar. A page that also needs other user data (the watchers
// page needs watchers, the feed needs matches) still fetches that itself — this only saves the `/me`
// call from being duplicated.
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, redirectToSignIn } = await auth();
  if (!isAuthenticated) return redirectToSignIn();

  // If the API is unreachable, degrade the sidebar rather than blocking the whole shell — the
  // page underneath already has its own "couldn't reach the API" state, and that message is more
  // useful than repeating it up here too.
  let me: Me | null = null;
  try {
    me = await apiFetch<Me>("/me");
  } catch {
    me = null;
  }

  return (
    <div className="flex h-svh overflow-hidden">
      <AppSidebar
        unreadMatches={me?.unread_matches ?? 0}
        plan={me?.user.plan ?? "free"}
        isSuperadmin={me?.user.is_superadmin ?? false}
        usage={
          me?.usage ?? {
            watchers_used: 0,
            watchers_limit: null,
            subreddits_used: 0,
            subreddits_limit: null,
          }
        }
      />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
