"use client";

import { useActionState, useEffect, useState } from "react";
import Link from "next/link";

import { createWatcherAction, type ActionState } from "@/app/actions/watchers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { WATCHER_TEMPLATES, type WatcherTemplate } from "@/lib/watcher-templates";

const INITIAL: ActionState = { error: null };

// The create-watcher form. Client-side only for the pending state, the reset-on-success and the
// template picker — the submission itself is a Server Action, so this works before hydration too.
//
// The fields are controlled so a template can fill them; a template is just a starting draft and
// every field stays editable afterwards.
export function WatcherForm({ onSuccess }: { onSuccess?: () => void } = {}) {
  const [name, setName] = useState("");
  const [intent, setIntent] = useState("");
  const [subreddits, setSubreddits] = useState("");
  const [templateId, setTemplateId] = useState<string | null>(null);

  // Clear the fields once a create succeeds. Leaving the old values in place makes it look like
  // nothing happened, since the new watcher appears further down the page. Done here rather than
  // in an effect so it is part of the same update as the result.
  const [state, action, pending] = useActionState(
    async (previous: ActionState, formData: FormData) => {
      const result = await createWatcherAction(previous, formData);
      if (result.ok) {
        setName("");
        setIntent("");
        setSubreddits("");
        setTemplateId(null);
      }
      return result;
    },
    INITIAL,
  );

  function applyTemplate(template: WatcherTemplate) {
    setTemplateId(template.id);
    setName(template.name);
    setIntent(template.intent_text);
    setSubreddits(template.subreddits.join(", "));
  }

  useEffect(() => {
    if (state.ok) {
      onSuccess?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.ok]);

  return (
    <form action={action} className="grid gap-4">
      <div className="grid gap-2">
        <Label>Start from a template</Label>
        <div className="flex flex-wrap gap-1.5">
          {WATCHER_TEMPLATES.map((template) => (
            <button
              key={template.id}
              type="button"
              aria-pressed={template.id === templateId}
              onClick={() => applyTemplate(template)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                template.id === templateId
                  ? "border-primary bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted",
              )}
            >
              {template.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Fills in the fields below as a draft — edit anything before you create it.
        </p>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="name">Name</Label>
        <Input
          id="name"
          name="name"
          required
          maxLength={200}
          placeholder="Freelance React work"
          value={name}
          onChange={(event) => setName(event.target.value)}
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
          value={intent}
          onChange={(event) => setIntent(event.target.value)}
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
          value={subreddits}
          onChange={(event) => setSubreddits(event.target.value)}
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
