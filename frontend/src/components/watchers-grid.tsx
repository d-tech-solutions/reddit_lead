"use client";

import { useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";

import { CreateWatcherDialog } from "@/components/create-watcher-dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { WatcherCard } from "@/components/watcher-card";
import type { Watcher } from "@/lib/types";

// The watchers page's grid: a search box, one card per watcher, and a trailing card that
// opens the create-watcher dialog. Search filters client-side over the already-loaded list —
// watcher counts are small enough that a round trip to the API would only add latency.
export function WatchersGrid({ watchers }: { watchers: Watcher[] }) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return watchers;
    return watchers.filter(
      (watcher) =>
        watcher.name.toLowerCase().includes(needle) ||
        watcher.intent_text.toLowerCase().includes(needle) ||
        watcher.subreddits.some((subreddit) => subreddit.toLowerCase().includes(needle)),
    );
  }, [watchers, query]);

  return (
    <div className="grid gap-6">
      <div className="relative max-w-xs">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search watchers…"
          className="pl-8"
        />
      </div>

      {watchers.length === 0 ? (
        <Card>
          <CardContent className="grid justify-items-center gap-3 py-10 text-center">
            <p className="text-sm text-muted-foreground">
              No watchers yet. Create one to start catching matching posts.
            </p>
            <CreateWatcherDialog>
              <button
                type="button"
                className="text-sm font-medium text-primary hover:underline"
              >
                Create your first watcher
              </button>
            </CreateWatcherDialog>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((watcher) => (
            <WatcherCard key={watcher.id} watcher={watcher} />
          ))}

          <CreateWatcherDialog>
            <button
              type="button"
              className="flex min-h-44 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border p-6 text-center transition-colors hover:border-primary/50 hover:bg-muted/40"
            >
              <span className="flex size-9 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <Plus className="size-4" />
              </span>
              <span className="text-sm font-medium">Create New Watcher</span>
              <span className="text-xs text-muted-foreground">
                Start monitoring a new intent topic across communities.
              </span>
            </button>
          </CreateWatcherDialog>
        </div>
      )}

      {watchers.length > 0 && filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No watchers match &quot;{query}&quot;.</p>
      ) : null}
    </div>
  );
}
