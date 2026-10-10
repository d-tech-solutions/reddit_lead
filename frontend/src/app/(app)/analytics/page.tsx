import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Analytics, DailyCount } from "@/lib/types";

const RANGES = [7, 30, 90] as const;
const DEFAULT_RANGE = 30;

function parseRange(value: string | undefined): number {
  const days = Number(value);
  return (RANGES as readonly number[]).includes(days) ? days : DEFAULT_RANGE;
}

function percent(rate: number | null): string {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`;
}

async function loadAnalytics(
  days: number,
): Promise<{ ok: true; data: Analytics } | { ok: false; status: number | null; message: string }> {
  try {
    return { ok: true, data: await apiFetch<Analytics>(`/analytics?days=${days}`) };
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, status: error.status, message: error.message };
    }
    return {
      ok: false,
      status: null,
      message: error instanceof Error ? error.message : "Unknown error",
    };
  }
}

function RangePicker({ days }: { days: number }) {
  return (
    <nav aria-label="Time range" className="flex gap-1 rounded-lg border p-1">
      {RANGES.map((range) => (
        <Link
          key={range}
          href={`/analytics?days=${range}`}
          aria-current={range === days ? "page" : undefined}
          className={cn(
            "rounded-md px-3 py-1 text-sm font-medium transition-colors",
            range === days
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          {range}d
        </Link>
      ))}
    </nav>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="grid gap-1 pt-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

// Plain bars rather than a chart library: one series, and the title on each bar is the tooltip.
function DailyChart({ daily }: { daily: DailyCount[] }) {
  const max = Math.max(1, ...daily.map((entry) => entry.confirmed));
  const first = daily[0]?.day;
  const last = daily[daily.length - 1]?.day;

  return (
    <div className="grid gap-2">
      <div className="flex h-40 items-end gap-px" role="img" aria-label="Confirmed matches per day">
        {daily.map((entry) => (
          <div
            key={entry.day}
            title={`${entry.day}: ${entry.confirmed}`}
            className="flex-1 rounded-t-sm bg-primary/80"
            style={{ height: `${entry.confirmed === 0 ? 2 : Math.max(4, (entry.confirmed / max) * 100)}%`, opacity: entry.confirmed === 0 ? 0.25 : 1 }}
          />
        ))}
      </div>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{first}</span>
        <span>{last}</span>
      </div>
    </div>
  );
}

function VerdictBar({
  confirmed,
  rejected,
}: {
  confirmed: number;
  rejected: number;
}) {
  const total = confirmed + rejected;
  if (total === 0) {
    return <p className="text-sm text-muted-foreground">Nothing has been reviewed yet.</p>;
  }
  const good = (confirmed / total) * 100;
  return (
    <div className="grid gap-2">
      <div className="flex h-3 overflow-hidden rounded-full bg-muted" role="img" aria-label={`${confirmed} confirmed, ${rejected} rejected`}>
        <div className="bg-primary" style={{ width: `${good}%` }} />
      </div>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{confirmed} confirmed</span>
        <span>{rejected} rejected</span>
      </div>
    </div>
  );
}

export default async function AnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days: daysParam } = await searchParams;
  const days = parseRange(daysParam);
  const result = await loadAnalytics(days);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 p-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold">Analytics</h1>
          <p className="text-sm text-muted-foreground">How your watchers have performed.</p>
        </div>
        <RangePicker days={days} />
      </header>

      {!result.ok ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Couldn&apos;t reach the API</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm text-muted-foreground">
            <p>
              {result.status ? `${result.status}: ` : ""}
              {result.message}
            </p>
            <p>
              Check the API is running: <code>docker compose up api</code>.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Dashboard data={result.data} />
      )}
    </div>
  );
}

function Dashboard({ data }: { data: Analytics }) {
  const { totals } = data;

  return (
    <>
      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Confirmed matches" value={String(totals.confirmed)} />
        <Stat label="Rejected by AI" value={String(totals.rejected)} />
        <Stat
          label="Match quality"
          value={percent(totals.pass_rate)}
          hint="Confirmed ÷ reviewed"
        />
        <Stat label="Awaiting review" value={String(totals.pending)} />
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Matches over time</CardTitle>
        </CardHeader>
        <CardContent>
          {totals.confirmed === 0 ? (
            <p className="text-sm text-muted-foreground">
              No confirmed matches in the last {data.days} days.
            </p>
          ) : (
            <DailyChart daily={data.daily} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Good vs bad matches</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <VerdictBar confirmed={totals.confirmed} rejected={totals.rejected} />
          <p className="text-xs text-muted-foreground">
            Based on the AI verifier&apos;s verdict on each candidate post. Your own thumbs up/down
            will replace this once match feedback is added.
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top subreddits</CardTitle>
          </CardHeader>
          <CardContent>
            {data.top_subreddits.length === 0 ? (
              <p className="text-sm text-muted-foreground">No confirmed matches yet.</p>
            ) : (
              <ol className="grid gap-2 text-sm">
                {data.top_subreddits.map((stat) => (
                  <li key={stat.subreddit} className="flex items-center justify-between gap-2">
                    <span className="truncate">r/{stat.subreddit}</span>
                    <span className="shrink-0 text-muted-foreground tabular-nums">
                      {stat.confirmed} · {percent(stat.pass_rate)}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Watcher performance</CardTitle>
          </CardHeader>
          <CardContent>
            {data.watchers.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No watchers yet.{" "}
                <Link href="/watchers" className="underline">
                  Create one
                </Link>
                .
              </p>
            ) : (
              <ul className="grid gap-3 text-sm">
                {data.watchers.map((watcher) => (
                  <li key={watcher.id} className="grid gap-0.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="truncate font-medium">{watcher.name}</span>
                        {watcher.status === "paused" ? <Badge variant="secondary">Paused</Badge> : null}
                      </span>
                      <span className="shrink-0 text-muted-foreground tabular-nums">
                        {watcher.confirmed} · {percent(watcher.pass_rate)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {watcher.last_match_at
                        ? `Last match ${new Date(watcher.last_match_at).toLocaleDateString()}`
                        : "No matches in this period"}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
