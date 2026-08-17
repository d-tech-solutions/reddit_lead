"use client";

import { useActionState, useEffect, useRef } from "react";

import { createWatcherAction, type ActionState } from "@/app/actions/watchers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const INITIAL: ActionState = { error: null };

// The create-watcher form. Client-side only for the pending state and the reset-on-success —
// the submission itself is a Server Action, so this works before hydration too.
export function WatcherForm() {
  const [state, action, pending] = useActionState(createWatcherAction, INITIAL);
  const formRef = useRef<HTMLFormElement>(null);

  // Clear the fields once a create succeeds. Leaving the old values in place makes it look like
  // nothing happened, since the new watcher appears further down the page.
  useEffect(() => {
    if (state.ok) {
      formRef.current?.reset();
    }
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
        <Label htmlFor="direction">I want to find people who are</Label>
        {/* Direction is a field rather than something inferred from the description: embeddings
            do not reliably encode which side of a transaction a post is on. */}
        <Select name="direction" defaultValue="requesting">
          <SelectTrigger id="direction">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="requesting">Requesting work (looking to hire)</SelectItem>
            <SelectItem value="offering">Offering work (advertising services)</SelectItem>
          </SelectContent>
        </Select>
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
          Describe it the way you would to a person. The more specific, the fewer false alarms.
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
