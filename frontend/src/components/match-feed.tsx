"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { loadMoreMatchesAction, markAllMatchesReadAction, markMatchReadAction } from "@/app/actions/matches";
import { MatchCard } from "@/components/match-card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { Match, Watcher } from "@/lib/types";

const DATE_RANGES = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "all", label: "All time" },
] as const;

type DateRange = (typeof DATE_RANGES)[number]["value"];

// A match's age in days, compared against the selected range. This filters only what has already
// been paged into the browser — it is a view over the loaded matches, not a query against the API,
// so "Load more" keeps working underneath it exactly as it did before the filter existed.
function withinRange(matchedAt: string, range: DateRange): boolean {
  if (range === "all") return true;
  const cutoff = Date.now() - Number(range) * 86_400_000;
  return new Date(matchedAt).getTime() >= cutoff;
}

// The paged list of matches, plus the watch/date filters shown above it.
//
// Holds the loaded pages in client state rather than re-rendering the route on every interaction:
// a user who has paged three times should not lose those pages because they opened one match.
export function MatchFeed({
  initialItems,
  initialCursor,
  initialUnread,
  watchers,
  selectedWatcherId,
}: {
  initialItems: Match[];
  initialCursor: string | null;
  initialUnread: number;
  watchers: Watcher[];
  selectedWatcherId: string | null;
}) {
  const router = useRouter();
  const [items, setItems] = useState(initialItems);
  const [cursor, setCursor] = useState(initialCursor);
  const [unread, setUnread] = useState(initialUnread);
  const [dateRange, setDateRange] = useState<DateRange>("7");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const visible = useMemo(
    () => items.filter((item) => withinRange(item.matched_at, dateRange)),
    [items, dateRange],
  );

  function loadMore() {
    setError(null);
    startTransition(async () => {
      if (!cursor) return;
      try {
        const page = await loadMoreMatchesAction(cursor);
        // Append rather than replace. The cursor guarantees no overlap with what is already here,
        // even if new matches arrived at the top of the feed since the page loaded.
        setItems((current) => [...current, ...page.items]);
        setCursor(page.next_cursor);
        setUnread(page.unread);
      } catch {
        setError("Couldn't load more. Try again.");
      }
    });
  }

  // Optimistic in the plain sense: the dot clears immediately and the request follows.
  // A failed mark-read is not worth interrupting someone who has just opened a Reddit tab, so it
  // only rolls the state back rather than showing an error.
  function open(id: string) {
    const target = items.find((item) => item.id === id);
    if (!target || target.read_at !== null) return;

    const stamped = new Date().toISOString();
    setItems((current) =>
      current.map((item) => (item.id === id ? { ...item, read_at: stamped } : item)),
    );
    setUnread((count) => Math.max(0, count - 1));

    startTransition(async () => {
      try {
        await markMatchReadAction(id);
      } catch {
        setItems((current) =>
          current.map((item) => (item.id === id ? { ...item, read_at: null } : item)),
        );
        setUnread((count) => count + 1);
      }
    });
  }

  function markAllRead() {
    setError(null);
    const previous = items;
    const stamped = new Date().toISOString();
    setItems((current) =>
      current.map((item) => (item.read_at === null ? { ...item, read_at: stamped } : item)),
    );
    setUnread(0);

    startTransition(async () => {
      try {
        await markAllMatchesReadAction();
      } catch {
        setItems(previous);
        setUnread(previous.filter((item) => item.read_at === null).length);
        setError("Couldn't mark everything read. Try again.");
      }
    });
  }

  function changeWatcher(watcherId: string | null) {
    router.push(!watcherId || watcherId === "all" ? "/matches" : `/matches?watcher_id=${watcherId}`);
  }

  return (
    <section className="grid gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto">
          <WatcherPill
            label="All"
            active={!selectedWatcherId}
            onClick={() => changeWatcher(null)}
          />
          {watchers.map((watcher) => (
            <WatcherPill
              key={watcher.id}
              label={watcher.name}
              active={selectedWatcherId === watcher.id}
              onClick={() => changeWatcher(watcher.id)}
            />
          ))}
        </div>

        <Select value={dateRange} onValueChange={(value) => setDateRange(value as DateRange)}>
          <SelectTrigger className="shrink-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DATE_RANGES.map((range) => (
              <SelectItem key={range.value} value={range.value}>
                Date: {range.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {unread > 0 ? (
          <Button variant="ghost" size="sm" disabled={pending} className="ml-auto" onClick={markAllRead}>
            Mark all read ({unread})
          </Button>
        ) : null}
      </div>

      {visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {items.length === 0
            ? "No matches for this watch yet."
            : "Nothing in that date range. Widen the date filter to see more."}
        </p>
      ) : (
        visible.map((match) => <MatchCard key={match.id} match={match} onOpen={open} />)
      )}

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {cursor ? (
        <div className="flex justify-center">
          <Button variant="outline" disabled={pending} onClick={loadMore}>
            {pending ? "Loading…" : "Load more"}
          </Button>
        </div>
      ) : null}
    </section>
  );
}

// One watcher filter option, rendered as a pill rather than a select item so switching watchers
// is a single click instead of an open-then-pick.
function WatcherPill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "shrink-0 rounded-full border px-3 py-1 text-sm font-medium whitespace-nowrap transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}
