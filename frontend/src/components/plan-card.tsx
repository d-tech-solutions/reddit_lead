import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PLAN_LABELS, formatQuota } from "@/lib/plan";
import type { Billing, Usage } from "@/lib/types";

// A read-only summary of the caller's plan and usage for the Settings page — price comparisons,
// upgrades, and the Stripe portal stay on /billing so this doesn't duplicate that page.
export function PlanCard({ billing, usage }: { billing: Billing; usage: Usage }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Plan</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3">
          <div>
            <Badge className="capitalize">{PLAN_LABELS[billing.plan] ?? billing.plan}</Badge>
            {billing.current_period_end ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {billing.cancel_at_period_end ? "Cancels" : "Renews"} on{" "}
                {new Date(billing.current_period_end).toLocaleDateString()}
              </p>
            ) : null}
          </div>
          <Button variant="outline" render={<Link href="/billing" />}>
            Manage plan
          </Button>
        </div>

        <div className="grid gap-1 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Watchers</span>
            <span className="font-medium">{formatQuota(usage.watchers_used, usage.watchers_limit)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Subreddits</span>
            <span className="font-medium">
              {formatQuota(usage.subreddits_used, usage.subreddits_limit)}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
