"use client";

import { useActionState, useEffect, useRef } from "react";
import Link from "next/link";

import { createWatcherAction, type ActionState } from "@/app/actions/watchers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const INITIAL: ActionState = { error: null };

// The create-watcher form. Client-side only for the pending state and the reset-on-success —
// the submission itself is a Server Action, so this works before hydration too.
export function WatcherForm({ onSuccess }: { onSuccess?: () => void } = {}) {
  const [state, action, pending] = useActionState(createWatcherAction, INITIAL);
  const formRef = useRef<HTMLFormElement>(null);

  // Clear the fields once a create succeeds. Leaving the old values in place makes it look like
  // nothing happened, since the new watcher appears further down the page.
  useEffect(() => {
    if (state.ok) {
      formRef.current?.reset();
      onSuccess?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.ok]);

  return (
    <form ref={formRef} action={action} className="grid gap-4">
      <div className="grid gap-2">
        <Label htmlFor="name">Name</Label>
        <Input
          id="name"
          name="name"
          required
          maxLength={200}
          placeholder="Freelance React work"
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="intent_text">What should I look for?</Label>
        <Textarea
          id="intent_text"
          name="intent_text"
          required
          minLength={15}
          maxLength={2000}
          rows={3}
          placeholder="Someone asking for a React developer to build or fix their web app"
        />
        <p className="text-xs text-muted-foreground">
          Describe it the way you would to a person — including whether they&apos;re looking to
          hire, offering their own services, or you just want to know about a topic. The more
          specific, the fewer false alarms.
        </p>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="subreddits">Subreddits</Label>
        <Input
          id="subreddits"
          name="subreddits"
          required
          placeholder="forhire, slavelabour"
        />
        <p className="text-xs text-muted-foreground">
          Separate with commas or spaces. The <code>r/</code> prefix is optional.
        </p>
      </div>

      {state.error ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {state.error}
          {state.status === 409 ? (
            <>
              {" "}
              <Link href="/settings" className="underline">
                Upgrade your plan
              </Link>
              .
            </>
          ) : null}
        </p>
      ) : null}

      <div>
        <Button type="submit" disabled={pending}>
          {pending ? "Creating…" : "Create watcher"}
        </Button>
      </div>
    </form>
  );
}
