"use client";

import { useActionState } from "react";

import { openPortalAction, startCheckoutAction, type ActionState } from "@/app/actions/billing";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PLAN_LABELS } from "@/lib/plan";
import type { Billing, Plan } from "@/lib/types";

const INITIAL: ActionState = { error: null };

function formatPrice(cents: number): string {
  return cents === 0 ? "Free" : `$${(cents / 100).toFixed(0)}/mo`;
}

function formatLimit(limit: number | null): string {
  return limit === null ? "Unlimited" : String(limit);
}

// A Checkout-session button for one paid plan. A Client Component (via the shared `useActionState`
// hook) only for the pending state and inline error — the mutation itself is a Server Action, so
// the Stripe secret key never reaches the browser.
function UpgradeButton({ plan }: { plan: "standard" | "premium" | "enterprise" }) {
  const [state, action, pending] = useActionState(startCheckoutAction.bind(null, plan), INITIAL);

  return (
    <form action={action} className="grid gap-1">
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Redirecting…" : "Upgrade"}
      </Button>
      {state.error ? <p className="text-xs text-destructive">{state.error}</p> : null}
    </form>
  );
}

function ManageBillingButton() {
  const [state, action, pending] = useActionState(openPortalAction, INITIAL);

  return (
    <form action={action} className="grid gap-1">
      <Button type="submit" variant="outline" disabled={pending}>
        {pending ? "Redirecting…" : "Manage billing"}
      </Button>
      {state.error ? <p className="text-xs text-destructive">{state.error}</p> : null}
    </form>
  );
}

// The current plan/renewal summary plus the pricing table, with an Upgrade button per paid tier
// and a Stripe-portal link once the user has a billing relationship at all.
export function BillingCard({ billing, plans }: { billing: Billing; plans: Plan[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Billing</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3">
          <div>
            <p className="text-sm font-medium capitalize">{billing.plan} plan</p>
            {billing.current_period_end ? (
              <p className="text-xs text-muted-foreground">
                {billing.cancel_at_period_end ? "Cancels" : "Renews"} on{" "}
                {new Date(billing.current_period_end).toLocaleDateString()}
              </p>
            ) : null}
          </div>
          {billing.plan !== "free" ? <ManageBillingButton /> : null}
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {plans.map((plan) => {
            const isCurrent = plan.id === billing.plan;
            return (
              <div key={plan.id} className="grid gap-2 rounded-lg border border-border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{PLAN_LABELS[plan.id] ?? plan.id}</span>
                  {isCurrent ? <Badge>Current</Badge> : null}
                </div>
                <p className="text-lg font-semibold">{formatPrice(plan.price_cents)}</p>
                <p className="text-xs text-muted-foreground">
                  {formatLimit(plan.max_watchers)} watchers · {formatLimit(plan.max_subreddits)}{" "}
                  subreddits
                </p>
                {plan.id === "free" || isCurrent ? (
                  <Button variant="outline" disabled className="w-full">
                    {isCurrent ? "Current plan" : "Included"}
                  </Button>
                ) : (
                  <UpgradeButton plan={plan.id as "standard" | "premium" | "enterprise"} />
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
