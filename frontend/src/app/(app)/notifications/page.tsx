import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NotificationsForm } from "@/components/notifications-form";
import { ApiError, apiFetch } from "@/lib/api";
import type { Settings } from "@/lib/types";

async function loadSettings(): Promise<
  { ok: true; settings: Settings } | { ok: false; status: number | null; message: string }
> {
  try {
    const settings = await apiFetch<Settings>("/settings");
    return { ok: true, settings };
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

export default async function NotificationsPage() {
  const result = await loadSettings();

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 p-8">
      <header className="grid gap-1">
        <h1 className="text-2xl font-semibold">Notifications</h1>
        <p className="text-sm text-muted-foreground">
          Control how and where PostPing notifies you about matches.
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
            <p>
              Check the API is running: <code>docker compose up api</code>.
            </p>
          </CardContent>
        </Card>
      ) : (
        <NotificationsForm settings={result.settings} />
      )}
    </div>
  );
}
