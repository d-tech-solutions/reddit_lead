import Link from "next/link";

import { MatchFeed } from "@/components/match-feed";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { MatchPage, Watcher } from "@/lib/types";

// Load the feed and the user's watchers together.
//
// The watchers are not decoration: an empty feed means different things depending on whether the
// user has any watchers, whether all of them are paused, or whether they are active and nothing
// has matched yet. Answering that needs both payloads. `watcherId` narrows the feed query itself —
// the API scopes it to the caller's watchers regardless, so this is purely "which one".
async function loadFeed(
  watcherId: string | null,
): Promise<
  | { ok: true; page: MatchPage; watchers: Watcher[] }
  | { ok: false; status: number | null; message: string }
> {
  try {
    const query = watcherId ? `?${new URLSearchParams({ watcher_id: watcherId }).toString()}` : "";
    const [page, watchers] = await Promise.all([
      apiFetch<MatchPage>(`/matches${query}`),
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

// Explain an empty, unfiltered feed honestly.
//
// One generic "no matches" message is the wrong answer here: the pipeline takes minutes to reach
// a new watcher, and a user who cannot tell "still warming up" from "working, nothing yet" will
// read both as broken. A feed that's empty only because of the watch/date filters is handled
// inside MatchFeed instead, since changing the filter is the fix and this component doesn't see it.
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
            <Link href="/watchers" className={buttonVariants({ size: "sm" })}>
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
          <Link href="/watchers" className="underline">
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

export default async function MatchesPage({
  searchParams,
}: {
  searchParams: Promise<{ watcher_id?: string }>;
}) {
  const { watcher_id: watcherId } = await searchParams;
  const result = await loadFeed(watcherId ?? null);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 p-8">
      <header className="grid gap-1">
        <h1 className="text-2xl font-semibold">Matches Feed</h1>
        <p className="text-sm text-muted-foreground">
          Posts your watchers caught, newest first.
        </p>
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
      ) : result.page.items.length === 0 && !watcherId ? (
        <EmptyState watchers={result.watchers} />
      ) : (
        <MatchFeed
          initialItems={result.page.items}
          initialCursor={result.page.next_cursor}
          initialUnread={result.page.unread}
          watchers={result.watchers}
          selectedWatcherId={watcherId ?? null}
        />
      )}
    </div>
  );
}
