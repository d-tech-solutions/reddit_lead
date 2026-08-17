"use client";

import { useState, useTransition } from "react";

import { deleteWatcherAction, setWatcherStatusAction } from "@/app/actions/watchers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Watcher } from "@/lib/types";

// One watcher, with its pause and delete controls.
//
// A Client Component because the controls are buttons rather than a form — the mutations
// themselves are still Server Actions, so nothing about the API or the token reaches the browser.
export function WatcherCard({ watcher }: { watcher: Watcher }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const paused = watcher.status === "paused";

  function run(action: () => Promise<void>) {
    setError(null);
    startTransition(async () => {
      try {
        await action();
      } catch {
        // The action already logged the detail server-side; the user just needs to know it failed.
        setError("That didn't work. Try again.");
      }
    });
  }

  return (
    <Card className={paused ? "opacity-70" : undefined}>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="grid gap-1">
          <CardTitle className="text-base">{watcher.name}</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">
              {watcher.direction === "offering" ? "Offering work" : "Requesting work"}
            </Badge>
            {paused ? <Badge variant="outline">Paused</Badge> : null}
            {/* Until the embedding worker has run, this watcher is invisible to the matcher. */}
            {watcher.embedded_at === null ? (
              <Badge variant="outline">Preparing…</Badge>
            ) : null}
          </div>
        </div>

        <div className="flex shrink-0 gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={pending}
            onClick={() =>
              run(() => setWatcherStatusAction(watcher.id, paused ? "active" : "paused"))
            }
          >
            {paused ? "Resume" : "Pause"}
          </Button>

          {confirmingDelete ? (
            <>
              <Button
                variant="destructive"
                size="sm"
                disabled={pending}
                onClick={() => run(() => deleteWatcherAction(watcher.id))}
              >
                Confirm
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={pending}
                onClick={() => setConfirmingDelete(false)}
              >
                Cancel
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              disabled={pending}
              onClick={() => setConfirmingDelete(true)}
            >
              Delete
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="grid gap-3">
        <p className="text-sm text-muted-foreground">{watcher.intent_text}</p>
        <div className="flex flex-wrap gap-1.5">
          {watcher.subreddits.map((subreddit) => (
            <Badge key={subreddit} variant="outline" className="font-mono text-xs">
              r/{subreddit}
            </Badge>
          ))}
        </div>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
