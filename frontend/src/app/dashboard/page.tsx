import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { UserButton } from "@clerk/nextjs";

import { WatcherCard } from "@/components/watcher-card";
import { WatcherForm } from "@/components/watcher-form";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { Me, Watcher } from "@/lib/types";

// Fetch the dashboard's two payloads together.
//
// Returns the failure rather than throwing so the page can explain what went wrong — a backend
// that is down or misconfigured is the single most likely thing to break in local development,
// and an unstyled error boundary tells the reader nothing about which of the two it was.
async function loadDashboard(): Promise<
  { ok: true; me: Me; watchers: Watcher[] } | { ok: false; status: number | null; message: string }
> {
  try {
    const [me, watchers] = await Promise.all([
      apiFetch<Me>("/me"),
      apiFetch<Watcher[]>("/watchers"),
    ]);
    return { ok: true, me, watchers };
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, status: error.status, message: error.message };
    }
    return {
      ok: false,
      status: null,
      message: error instanceof Error ? error.message : "Unknown error",
    };
  }
}

// Render "2 of 3" — or just the number when the plan is unbounded.
function quota(used: number, limit: number | null): string {
  return limit === null ? `${used}` : `${used} of ${limit}`;
}

export default async function DashboardPage() {
  const { isAuthenticated, redirectToSignIn } = await auth();
  if (!isAuthenticated) return redirectToSignIn();

  const result = await loadDashboard();

  if (!result.ok) {
    return (
      <div className="flex flex-1 flex-col gap-6 p-8">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Watchers</h1>
          <UserButton />
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Couldn&apos;t reach the API</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm text-muted-foreground">
            <p>
              {result.status ? `${result.status}: ` : ""}
              {result.message}
            </p>
            {result.status === 500 ? (
              <p>
                If this mentions <code>CLERK_SECRET_KEY</code>, the API has no Clerk secret to
                verify tokens with — set it in the root <code>.env</code> and restart the API.
              </p>
            ) : (
              <p>
                Check the API is running: <code>docker compose up api</code>.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  const { me, watchers } = result;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-8">
      <header className="flex items-center justify-between">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold">Watchers</h1>
          <p className="text-sm text-muted-foreground">
            <Badge variant="secondary" className="mr-2 capitalize">
              {me.user.plan}
            </Badge>
            {quota(me.usage.watchers_used, me.usage.watchers_limit)} watchers ·{" "}
            {quota(me.usage.subreddits_used, me.usage.subreddits_limit)} subreddits
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* `buttonVariants` on the Link rather than a Button wrapping it: this project's Button
              is Base UI, which has no `asChild`, and a nav item should render as an anchor. */}
          <Link href="/matches" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            Matches
            {/* The count comes back with /me, so the badge costs no extra request. */}
            {me.unread_matches > 0 ? <Badge className="ml-2">{me.unread_matches}</Badge> : null}
          </Link>
          <UserButton />
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">New watcher</CardTitle>
        </CardHeader>
        <CardContent>
          <WatcherForm />
        </CardContent>
      </Card>

      <section className="grid gap-4">
        {watchers.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">No watchers yet</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Create one above and PostPing will start watching those subreddits for posts matching
              your description.
            </CardContent>
          </Card>
        ) : (
          watchers.map((watcher) => <WatcherCard key={watcher.id} watcher={watcher} />)
        )}
      </section>
    </div>
  );
}
