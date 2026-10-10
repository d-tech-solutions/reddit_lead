"use client";

import { useState, useTransition } from "react";
import { MoreVertical } from "lucide-react";

import { deleteWatcherAction, setWatcherStatusAction } from "@/app/actions/watchers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import type { Watcher } from "@/lib/types";

// One watcher: its description, subreddits, an active/paused toggle, and a delete tucked behind
// a kebab menu since it is the one destructive action here.
//
// A Client Component because the controls are interactive — the mutations themselves are still
// Server Actions, so nothing about the API or the token reaches the browser.
export function WatcherCard({ watcher }: { watcher: Watcher }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const active = watcher.status === "active";

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

  function closeMenu() {
    setMenuOpen(false);
    setConfirmingDelete(false);
  }

  return (
    <Card className={active ? undefined : "opacity-70"}>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <CardTitle className="text-base">{watcher.name}</CardTitle>

        <div className="relative shrink-0">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Watcher actions"
            disabled={pending}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <MoreVertical className="size-4" />
          </Button>

          {menuOpen ? (
            <>
              {/* Catches outside clicks to close the menu, without pulling in a full popover primitive
                  for what is otherwise a one-item menu. */}
              <button
                type="button"
                aria-hidden
                tabIndex={-1}
                className="fixed inset-0 z-10 cursor-default"
                onClick={closeMenu}
              />
              <div className="absolute top-full right-0 z-20 mt-1 min-w-40 rounded-lg bg-popover p-1 text-sm shadow-md ring-1 ring-foreground/10">
                {confirmingDelete ? (
                  <div className="grid gap-1 p-1">
                    <p className="px-1.5 py-1 text-xs text-muted-foreground">Delete this watcher?</p>
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={pending}
                      onClick={() => run(() => deleteWatcherAction(watcher.id))}
                    >
                      Confirm delete
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setConfirmingDelete(false)}>
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="block w-full rounded-md px-2 py-1.5 text-left text-destructive hover:bg-destructive/10"
                    onClick={() => setConfirmingDelete(true)}
                  >
                    Delete
                  </button>
                )}
              </div>
            </>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="grid gap-3">
        <p className="line-clamp-2 text-sm text-muted-foreground">{watcher.intent_text}</p>

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

        <div className="flex items-center gap-2 border-t border-border pt-3">
          <Switch
            checked={active}
            disabled={pending}
            onCheckedChange={(checked) =>
              run(() => setWatcherStatusAction(watcher.id, checked ? "active" : "paused"))
            }
          />
          <span className="text-sm text-muted-foreground">{active ? "Active" : "Paused"}</span>
        </div>
      </CardContent>
    </Card>
  );
}
