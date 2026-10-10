"use client";

import Link from "next/link";
import { useActionState } from "react";

import {
  createTelegramLinkAction,
  disconnectChannelAction,
  setChannelEnabledAction,
  testChannelAction,
  type ActionState,
} from "@/app/actions/settings";
import { ActionFeedback } from "@/components/action-feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { NotificationChannel } from "@/lib/types";

const INITIAL: ActionState = { error: null };

// Telegram alert settings. Paid plans only; free accounts see an upgrade prompt instead.
//
// Connecting happens in Telegram, not on this page: "Connect" mints a one-time link, the user opens
// it and presses Start, and the bot tells our API. That means this page can't see the result
// immediately — after opening the link, the user reloads (or comes back) to see "Connected".
export function TelegramCard({
  channel,
  canUse,
}: {
  channel: NotificationChannel | undefined;
  canUse: boolean;
}) {
  const [linkState, createLink, linking] = useActionState(createTelegramLinkAction, INITIAL);
  const [toggleState, toggle, toggling] = useActionState(setChannelEnabledAction, INITIAL);
  const [testState, test, testing] = useActionState(testChannelAction, INITIAL);
  const [disconnectState, disconnect, disconnecting] = useActionState(
    disconnectChannelAction,
    INITIAL,
  );

  const connected = channel?.verified === true;
  const waiting = channel !== undefined && !connected && channel.link_pending;
  const needsReconnect = channel !== undefined && !connected && !channel.link_pending;
  const busy = linking || toggling || testing || disconnecting;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="text-base">Telegram</CardTitle>
        {!canUse ? (
          <Badge variant="outline">Paid plans</Badge>
        ) : connected ? (
          <Badge variant="secondary">{channel.enabled ? "Connected" : "Paused"}</Badge>
        ) : waiting ? (
          <Badge variant="outline">Waiting for Start</Badge>
        ) : needsReconnect ? (
          <Badge variant="destructive">Needs reconnect</Badge>
        ) : (
          <Badge variant="outline">Not connected</Badge>
        )}
      </CardHeader>
      <CardContent className="grid gap-4">
        {!canUse ? (
          <p className="text-sm text-muted-foreground">
            Telegram alerts are included with paid plans.{" "}
            <Link href="/billing" className="underline">
              See plans
            </Link>
            .
          </p>
        ) : (
          <>
            {connected ? (
              <div className="flex flex-wrap gap-2">
                <form action={toggle}>
                  <input type="hidden" name="channel_type" value="telegram" />
                  <input type="hidden" name="enabled" value={String(!channel.enabled)} />
                  <Button type="submit" variant="outline" size="sm" disabled={busy}>
                    {channel.enabled ? "Pause alerts" : "Resume alerts"}
                  </Button>
                </form>
                <form action={test}>
                  <input type="hidden" name="channel_type" value="telegram" />
                  <Button type="submit" variant="outline" size="sm" disabled={busy}>
                    {testing ? "Sending…" : "Send test"}
                  </Button>
                </form>
                <form action={disconnect}>
                  <input type="hidden" name="channel_type" value="telegram" />
                  <Button type="submit" variant="ghost" size="sm" disabled={busy}>
                    Disconnect
                  </Button>
                </form>
              </div>
            ) : null}

            {linkState.url ? (
              <div className="grid gap-2 rounded-md border border-border p-3 text-sm">
                <p>
                  Open the link, press <strong>Start</strong> in Telegram, then reload this page.
                </p>
                <a
                  href={linkState.url}
                  target="_blank"
                  rel="noreferrer"
                  className="w-fit font-medium underline"
                >
                  Open Telegram
                </a>
              </div>
            ) : waiting ? (
              <p className="text-sm text-muted-foreground">
                A link was created but isn&apos;t shown again for security. If you haven&apos;t
                pressed Start yet, get a new link.
              </p>
            ) : null}

            <form action={createLink}>
              <Button type="submit" variant={connected ? "outline" : "default"} disabled={busy}>
                {linking
                  ? "Creating link…"
                  : connected
                    ? "Connect a different chat"
                    : waiting || needsReconnect
                      ? "Get a new link"
                      : "Connect Telegram"}
              </Button>
            </form>

            <p className="text-xs text-muted-foreground">
              Alerts go to your private chat with the PostPing bot, one message per match.
            </p>
          </>
        )}

        <ActionFeedback state={linkState} />
        <ActionFeedback state={toggleState} />
        <ActionFeedback state={testState} />
        <ActionFeedback state={disconnectState} />
      </CardContent>
    </Card>
  );
}
