// Shared between account-card, billing-card, plan-card, and the sidebar so the plan display
// logic doesn't drift between them.

export const PLAN_LABELS: Record<string, string> = {
  free: "Free",
  standard: "Standard",
  premium: "Premium",
  enterprise: "Enterprise",
};

// Render "2/3" — or just the number when the plan is unbounded.
export function formatQuota(used: number, limit: number | null): string {
  return limit === null ? `${used}` : `${used}/${limit}`;
}
