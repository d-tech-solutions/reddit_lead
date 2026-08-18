import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { UserButton } from "@clerk/nextjs";

import { MatchFeed } from "@/components/match-feed";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { MatchPage, Watcher } from "@/lib/types";

// Load the feed and the user's watchers together.
//
// The watchers are not decoration: an empty feed means different things depending on whether the
// user has any watchers, whether all of them are paused, or whether they are active and nothing
// has matched yet. Answering that needs both payloads.
async function loadFeed(): Promise<
  | { ok: true; page: MatchPage; watchers: Watcher[] }
  | { ok: false; status: number | null; message: string }
> {
  try {
    const [page, watchers] = await Promise.all([
      apiFetch<MatchPage>("/matches"),
      apiFetch<Watcher[]>("/watchers"),
    ]);
    return { ok: true, page, watchers };
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

// Explain an empty feed honestly.
//
// One generic "no matches" message is the wrong answer here: the pipeline takes minutes to reach
// a new watcher, and a user who cannot tell "still warming up" from "working, nothing yet" will
// read both as broken.
function EmptyState({ watchers }: { watchers: Watcher[] }) {
  if (watchers.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">No watchers yet</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm text-muted-foreground">
          <p>Matches show up here once you tell PostPing what to watch for.</p>
          <div>
            <Link href="/dashboard" className={buttonVariants({ size: "sm" })}>
              Create a watcher
            </Link>
          </div>
        </CardContent>
      </Card>
    );
  }

  const active = watchers.filter((watcher) => watcher.status === "active");

  if (active.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">All your watchers are paused</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Paused watchers do not look at new posts. Resume one on the{" "}
          <Link href="/dashboard" className="underline">
            watchers page
          </Link>{" "}
          to start catching matches again.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Watching now</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Nothing has matched yet. PostPing is checking{" "}
        {active.length === 1 ? "your watcher" : `all ${active.length} of your watchers`} against
        new posts as they appear — this page fills in on its own.
      </CardContent>
    </Card>
  );
}

export default async function MatchesPage() {
  const { isAuthenticated, redirectToSignIn } = await auth();
  if (!isAuthenticated) return redirectToSignIn();

  const result = await loadFeed();

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-8">
      <header className="flex items-center justify-between">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold">Matches</h1>
          <p className="text-sm text-muted-foreground">
            Posts your watchers caught, newest first.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            Watchers
          </Link>
          <UserButton />
        </div>
      </header>

      {!result.ok ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Couldn&apos;t reach the API</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm text-muted-foreground">
            <p>
              {result.status ? `${result.status}: ` : ""}
              {result.message}
            </p>
            <p>
              Check the API is running: <code>docker compose up api</code>.
            </p>
          </CardContent>
        </Card>
      ) : result.page.items.length === 0 ? (
        <EmptyState watchers={result.watchers} />
      ) : (
        <MatchFeed
          initialItems={result.page.items}
          initialCursor={result.page.next_cursor}
          initialUnread={result.page.unread}
        />
      )}
    </div>
  );
}
