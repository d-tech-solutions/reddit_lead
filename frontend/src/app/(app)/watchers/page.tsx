import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { WatchersGrid } from "@/components/watchers-grid";
import { ApiError, apiFetch } from "@/lib/api";
import type { Watcher } from "@/lib/types";

async function loadWatchers(): Promise<
  { ok: true; watchers: Watcher[] } | { ok: false; status: number | null; message: string }
> {
  try {
    const watchers = await apiFetch<Watcher[]>("/watchers");
    return { ok: true, watchers };
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

export default async function WatchersPage() {
  const result = await loadWatchers();

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 p-8">
      <header className="grid gap-1">
        <h1 className="text-2xl font-semibold">My Watches</h1>
        <p className="text-sm text-muted-foreground">
          Manage and monitor your active intent trackers.
        </p>
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
            {result.status === 500 ? (
              <p>
                If this mentions <code>CLERK_SECRET_KEY</code>, the API has no Clerk secret to
                verify tokens with — set it in the root <code>.env</code> and restart the API.
              </p>
            ) : (
              <p>
                Check the API is running: <code>docker compose up api</code>.
              </p>
            )}
          </CardContent>
        </Card>
      ) : (
        <WatchersGrid watchers={result.watchers} />
      )}
    </div>
  );
}
