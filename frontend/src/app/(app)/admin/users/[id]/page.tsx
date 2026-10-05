import Link from "next/link";
import { notFound } from "next/navigation";

import { AdminUserActions } from "@/components/admin-user-actions";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { PLAN_LABELS } from "@/lib/plan";
import type { AdminUserDetail } from "@/lib/types";

async function loadUser(id: string): Promise<AdminUserDetail> {
  try {
    return await apiFetch<AdminUserDetail>(`/admin/users/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
}

export default async function AdminUserDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const user = await loadUser(id);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-8">
      <div>
        <Link href="/admin" className="text-sm text-muted-foreground hover:underline">
          ← All users
        </Link>
      </div>

      <header className="grid gap-1">
        <h1 className="text-2xl font-semibold">{user.email ?? "(no email on file)"}</h1>
        <p className="text-sm text-muted-foreground">
          {PLAN_LABELS[user.plan] ?? user.plan} · joined{" "}
          {new Date(user.created_at).toLocaleDateString()}
          {user.is_superadmin ? " · admin" : ""}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Account</CardTitle>
        </CardHeader>
        <CardContent>
          <AdminUserActions user={user} redirectOnDeleteTo="/admin" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Watchers ({user.watchers.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          {user.watchers.length === 0 ? (
            <p className="text-sm text-muted-foreground">This user hasn&apos;t created any.</p>
          ) : (
            user.watchers.map((watcher) => (
              <div key={watcher.id} className="grid gap-1.5 rounded-lg border border-border p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{watcher.name}</p>
                  <Badge variant={watcher.status === "active" ? "default" : "outline"}>
                    {watcher.status}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">{watcher.intent_text}</p>
                <div className="flex flex-wrap gap-1.5">
                  {watcher.subreddits.map((subreddit) => (
                    <Badge key={subreddit} variant="outline" className="font-mono text-xs">
                      r/{subreddit}
                    </Badge>
                  ))}
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
