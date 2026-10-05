import Link from "next/link";

import { AccountCard } from "@/components/account-card";
import { PlanCard } from "@/components/plan-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { Billing, Me } from "@/lib/types";

async function loadMe(): Promise<
  { ok: true; me: Me } | { ok: false; status: number | null; message: string }
> {
  try {
    const me = await apiFetch<Me>("/me");
    return { ok: true, me };
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

async function loadBilling(): Promise<{ ok: true; billing: Billing } | { ok: false }> {
  try {
    const billing = await apiFetch<Billing>("/billing");
    return { ok: true, billing };
  } catch {
    return { ok: false };
  }
}

export default async function SettingsPage() {
  const [meResult, billingResult] = await Promise.all([loadMe(), loadBilling()]);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 p-8">
      <header className="grid gap-1">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your account.</p>
      </header>

      {!meResult.ok ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Couldn&apos;t reach the API</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm text-muted-foreground">
            <p>
              {meResult.status ? `${meResult.status}: ` : ""}
              {meResult.message}
            </p>
            <p>
              Check the API is running: <code>docker compose up api</code>.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <AccountCard email={meResult.me.user.email} />
          {billingResult.ok ? (
            <PlanCard billing={billingResult.billing} usage={meResult.me.usage} />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Plan</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                Couldn&apos;t load your plan details.{" "}
                <Link href="/billing" className="text-primary underline-offset-4 hover:underline">
                  View them on the Billing page
                </Link>
                .
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
