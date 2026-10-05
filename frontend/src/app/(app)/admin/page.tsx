import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { AdminUser } from "@/lib/types";

async function loadUsers(): Promise<
  { ok: true; users: AdminUser[] } | { ok: false; status: number | null; message: string }
> {
  try {
    const users = await apiFetch<AdminUser[]>("/admin/users");
    return { ok: true, users };
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

export default async function AdminUsersPage() {
  const result = await loadUsers();

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-8">
      <header className="grid gap-1">
        <h1 className="text-2xl font-semibold">Users</h1>
        <p className="text-sm text-muted-foreground">
          Every PostPing account and whether it&apos;s active.
        </p>
      </header>

      {!result.ok ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Couldn&apos;t reach the API</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {result.status ? `${result.status}: ` : ""}
            {result.message}
          </CardContent>
        </Card>
      ) : result.users.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No users yet</CardTitle>
          </CardHeader>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Email</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {result.users.map((user) => (
                  <tr key={user.id} className="border-b last:border-0">
                    <td className="px-4 py-3">
                      <Link href={`/admin/users/${user.id}`} className="hover:underline">
                        {user.email ?? "(no email on file)"}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{user.is_active ? "Active" : "Deactivated"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
