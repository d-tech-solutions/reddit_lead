"use client";

import { ExternalLink, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { Match } from "@/lib/types";

// Turn a timestamp into "3h ago".
//
// Deliberately coarse: a match feed is read in glances, and the exact minute never changes what
// the reader does next. The full timestamp stays in the `title` attribute for anyone who wants it.
function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

// One confirmed match: the post, which watcher caught it, and why the verifier said yes.
//
// Opening the Reddit link is what marks it read — that is the moment the user has actually seen
// it, and it saves a second click on the thing they were going to click anyway.
export function MatchCard({
  match,
  onOpen,
}: {
  match: Match;
  onOpen: (id: string) => void;
}) {
  const unread = match.read_at === null;

  return (
    <Card className={unread ? "border-primary/40" : undefined}>
      <CardHeader className="gap-2 space-y-0">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="font-mono">
            r/{match.post.subreddit}
          </Badge>
          <span>
            Watch: <span className="text-foreground">&quot;{match.watcher.name}&quot;</span>
          </span>
          <span className="ml-auto shrink-0">
            {/* Server and client can render this a minute apart if the page sits between a
                boundary; the mismatch is cosmetic and this is the narrow fix for it. */}
            <time
              dateTime={match.matched_at}
              title={new Date(match.matched_at).toLocaleString()}
              suppressHydrationWarning
            >
              {timeAgo(match.matched_at)}
            </time>
          </span>
        </div>

        <div className="flex items-start gap-2">
          <h3 className="text-base leading-snug font-medium">{match.post.title}</h3>
          {unread ? (
            <span aria-label="Unread" className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" />
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="grid gap-3 text-sm">
        {match.reason ? (
          <div className="flex gap-2 rounded-lg bg-primary/10 p-3 text-primary">
            <Sparkles className="mt-0.5 size-4 shrink-0" />
            <p className="text-foreground/90">
              <span className="font-medium text-primary">AI Match: </span>
              <span className="italic">{match.reason}</span>
            </p>
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-3">
          {match.post.author ? (
            <span className="text-xs text-muted-foreground">u/{match.post.author}</span>
          ) : (
            <span />
          )}
          <Button
            variant="outline"
            size="sm"
            render={
              <a
                href={match.post.permalink}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => onOpen(match.id)}
              />
            }
          >
            View on Reddit
            <ExternalLink className="size-3.5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
