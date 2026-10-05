"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { loadMorePostsAction } from "@/app/actions/posts";
import { PostCard } from "@/components/post-card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Post } from "@/lib/types";

// The paged list of ingested posts, plus the subreddit chip selector shown above it.
//
// Holds the loaded pages in client state rather than re-rendering the route on every interaction —
// same reasoning as MatchFeed — so "Load more" survives everything except an actual subreddit
// switch, which is the one interaction that has to hit the server for a different scope.
export function PostFeed({
  initialItems,
  initialCursor,
  subreddits,
  selectedSubreddit,
}: {
  initialItems: Post[];
  initialCursor: string | null;
  subreddits: string[];
  selectedSubreddit: string | null;
}) {
  const router = useRouter();
  const [items, setItems] = useState(initialItems);
  const [cursor, setCursor] = useState(initialCursor);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function loadMore() {
    setError(null);
    startTransition(async () => {
      if (!cursor) return;
      try {
        const page = await loadMorePostsAction(cursor, selectedSubreddit);
        // Append rather than replace. The cursor guarantees no overlap with what is already here,
        // even if new posts arrived at the top of the feed since the page loaded.
        setItems((current) => [...current, ...page.items]);
        setCursor(page.next_cursor);
      } catch {
        setError("Couldn't load more. Try again.");
      }
    });
  }

  function changeSubreddit(subreddit: string | null) {
    router.push(!subreddit ? "/posts" : `/posts?subreddit=${subreddit}`);
  }

  return (
    <section className="grid gap-4">
      <div className="flex min-w-0 flex-wrap gap-1.5">
        <SubredditPill
          label="All"
          active={!selectedSubreddit}
          onClick={() => changeSubreddit(null)}
        />
        {subreddits.map((subreddit) => (
          <SubredditPill
            key={subreddit}
            label={`r/${subreddit}`}
            active={selectedSubreddit === subreddit}
            onClick={() => changeSubreddit(subreddit)}
          />
        ))}
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No posts fetched for this subreddit yet.
        </p>
      ) : (
        items.map((post) => <PostCard key={post.id} post={post} />)
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

// One subreddit filter option, rendered as a pill rather than a select item — mirrors the watcher
// pill on the matches feed, so switching subreddits is a single click.
function SubredditPill({
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
