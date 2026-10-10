"use client";

import { useActionState } from "react";

import { updateSettingsAction, type ActionState } from "@/app/actions/settings";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { Settings } from "@/lib/types";

const INITIAL: ActionState = { error: null };

// Notification-channel settings: where alerts go and which channels are on.
//
// A Client Component for the pending state on the form — the mutation itself is a Server Action,
// so the API token never reaches the browser.
export function NotificationsForm({ settings }: { settings: Settings }) {
  const emailChannel = settings.channels.find((channel) => channel.channel_type === "email");
  const [state, action, pending] = useActionState(updateSettingsAction, INITIAL);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Notifications</CardTitle>
      </CardHeader>
      <CardContent>
        <form action={action} className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="notification_email">Notification email</Label>
            <Input
              id="notification_email"
              name="notification_email"
              type="email"
              defaultValue={settings.notification_email ?? ""}
              placeholder={settings.account_email ?? "you@example.com"}
            />
            <p className="text-xs text-muted-foreground">
              Where match alerts are sent. Leave blank to use your account email
              {settings.account_email ? ` (${settings.account_email})` : ""}.
            </p>
          </div>

          <div className="flex items-center gap-2 border-t border-border pt-4">
            <Switch
              name="email_enabled"
              defaultChecked={emailChannel?.enabled ?? true}
              disabled={pending}
            />
            <span className="text-sm text-muted-foreground">Email notifications</span>
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
              {pending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
