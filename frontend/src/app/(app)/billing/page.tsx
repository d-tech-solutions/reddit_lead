import { BillingCard } from "@/components/billing-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { Billing, Plan } from "@/lib/types";

async function loadBilling(): Promise<
  { ok: true; billing: Billing; plans: Plan[] } | { ok: false; status: number | null; message: string }
> {
  try {
    const [billing, plans] = await Promise.all([
      apiFetch<Billing>("/billing"),
      apiFetch<Plan[]>("/billing/plans"),
    ]);
    return { ok: true, billing, plans };
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

export default async function BillingPage() {
  const result = await loadBilling();

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 p-8">
      <header className="grid gap-1">
        <h1 className="text-2xl font-semibold">Billing</h1>
        <p className="text-sm text-muted-foreground">
          Manage your plan and payment details.
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
        <BillingCard billing={result.billing} plans={result.plans} />
      )}
    </div>
  );
}
