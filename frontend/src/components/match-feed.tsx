"use client";

import { useState, useTransition } from "react";

import { loadMoreMatchesAction, markAllMatchesReadAction, markMatchReadAction } from "@/app/actions/matches";
import { MatchCard } from "@/components/match-card";
import { Button } from "@/components/ui/button";
import type { Match } from "@/lib/types";

// The paged list of matches.
//
// Holds the loaded pages in client state rather than re-rendering the route on every interaction:
// a user who has paged three times should not lose those pages because they opened one match.
export function MatchFeed({
  initialItems,
  initialCursor,
  initialUnread,
}: {
  initialItems: Match[];
  initialCursor: string | null;
  initialUnread: number;
}) {
  const [items, setItems] = useState(initialItems);
  const [cursor, setCursor] = useState(initialCursor);
  const [unread, setUnread] = useState(initialUnread);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

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

  return (
    <section className="grid gap-4">
      {unread > 0 ? (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {unread} unread {unread === 1 ? "match" : "matches"}
          </p>
          <Button variant="ghost" size="sm" disabled={pending} onClick={markAllRead}>
            Mark all read
          </Button>
        </div>
      ) : null}

      {items.map((match) => (
        <MatchCard key={match.id} match={match} onOpen={open} />
      ))}

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
