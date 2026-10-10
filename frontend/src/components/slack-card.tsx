"use client";

import { useActionState } from "react";

import {
  connectSlackAction,
  disconnectChannelAction,
  setChannelEnabledAction,
  testChannelAction,
  type ActionState,
} from "@/app/actions/settings";
import { ActionFeedback } from "@/components/action-feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { NotificationChannel } from "@/lib/types";

const INITIAL: ActionState = { error: null };

// Slack alert settings: connect with a pasted incoming-webhook URL, then pause, test or remove it.
//
// The webhook URL is write-only — the API never sends it back — so a connected card has nothing
// to prefill, and replacing it means pasting a new one.
export function SlackCard({ channel }: { channel: NotificationChannel | undefined }) {
  const [connectState, connect, connecting] = useActionState(connectSlackAction, INITIAL);
  const [toggleState, toggle, toggling] = useActionState(setChannelEnabledAction, INITIAL);
  const [testState, test, testing] = useActionState(testChannelAction, INITIAL);
  const [disconnectState, disconnect, disconnecting] = useActionState(
    disconnectChannelAction,
    INITIAL,
  );

  const connected = channel !== undefined;
  const needsReconnect = connected && !channel.verified;
  const busy = connecting || toggling || testing || disconnecting;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="text-base">Slack</CardTitle>
        {needsReconnect ? (
          <Badge variant="destructive">Needs reconnect</Badge>
        ) : connected ? (
          <Badge variant="secondary">{channel.enabled ? "Connected" : "Paused"}</Badge>
        ) : (
          <Badge variant="outline">Not connected</Badge>
        )}
      </CardHeader>
      <CardContent className="grid gap-4">
        {connected && !needsReconnect ? (
          <div className="flex flex-wrap gap-2">
            <form action={toggle}>
              <input type="hidden" name="channel_type" value="slack" />
              <input type="hidden" name="enabled" value={String(!channel.enabled)} />
              <Button type="submit" variant="outline" size="sm" disabled={busy}>
                {channel.enabled ? "Pause alerts" : "Resume alerts"}
              </Button>
            </form>
            <form action={test}>
              <input type="hidden" name="channel_type" value="slack" />
              <Button type="submit" variant="outline" size="sm" disabled={busy}>
                {testing ? "Sending…" : "Send test"}
              </Button>
            </form>
            <form action={disconnect}>
              <input type="hidden" name="channel_type" value="slack" />
              <Button type="submit" variant="ghost" size="sm" disabled={busy}>
                Disconnect
              </Button>
            </form>
          </div>
        ) : null}

        <form action={connect} className="grid gap-2">
          <Label htmlFor="slack_webhook_url">
            {connected ? "Replace webhook URL" : "Incoming webhook URL"}
          </Label>
          <div className="flex gap-2">
            <Input
              id="slack_webhook_url"
              name="webhook_url"
              type="password"
              autoComplete="off"
              placeholder="https://hooks.slack.com/services/…"
              disabled={busy}
            />
            <Button type="submit" disabled={busy}>
              {connecting ? "Connecting…" : connected ? "Replace" : "Connect"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Create an{" "}
            <a
              href="https://api.slack.com/messaging/webhooks"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              incoming webhook
            </a>{" "}
            for the channel you want alerts in and paste its URL here. We post a test message to
            check it works.
          </p>
        </form>

        <ActionFeedback state={connectState} />
        <ActionFeedback state={toggleState} />
        <ActionFeedback state={testState} />
        <ActionFeedback state={disconnectState} />
      </CardContent>
    </Card>
  );
}
