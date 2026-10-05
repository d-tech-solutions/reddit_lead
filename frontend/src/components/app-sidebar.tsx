"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserButton } from "@clerk/nextjs";
import {
  Bell,
  BellRing,
  CreditCard,
  LayoutGrid,
  Plus,
  Rss,
  Settings,
  Shield,
} from "lucide-react";

import { CreateWatcherDialog } from "@/components/create-watcher-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatQuota } from "@/lib/plan";
import type { Usage } from "@/lib/types";

const NAV_ITEMS = [
  { href: "/watchers", label: "Watchers", icon: LayoutGrid },
  { href: "/matches", label: "Matches", icon: Bell },
  { href: "/notifications", label: "Notifications", icon: BellRing },
  { href: "/billing", label: "Billing", icon: CreditCard },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

// Staff-only: hidden from the nav (and from `/admin`'s own route, via the admin layout guard)
// for anyone whose account isn't flagged `is_superadmin`.
const ADMIN_NAV_ITEMS = [
  { href: "/admin", label: "Users", icon: Shield },
  { href: "/posts", label: "Posts", icon: Rss },
] as const;

// The persistent app shell nav: brand, the create-watcher entry point, the section links, and
// account controls. A Client Component so the active link can react to the current route.
export function AppSidebar({
  unreadMatches,
  plan,
  usage,
  isSuperadmin,
}: {
  unreadMatches: number;
  plan: string;
  usage: Usage;
  isSuperadmin: boolean;
}) {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 min-h-0 shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-4 py-5 text-sidebar-foreground">
      <Link href="/watchers" className="mb-6 block shrink-0 px-2">
        <span className="text-lg font-semibold tracking-tight text-primary">PostPing</span>
        <p className="text-xs text-muted-foreground">Reddit intent alerts</p>
      </Link>

      <CreateWatcherDialog>
        <Button className="mb-6 w-full shrink-0 justify-center gap-1.5">
          <Plus className="size-4" />
          New Watcher
        </Button>
      </CreateWatcherDialog>

      <nav className="grid min-h-0 flex-1 auto-rows-min gap-1 overflow-y-auto">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <NavLink
            key={href}
            href={href}
            label={label}
            icon={Icon}
            active={pathname === href}
            badge={href === "/matches" && unreadMatches > 0 ? unreadMatches : undefined}
          />
        ))}

        {isSuperadmin ? (
          <>
            <p className="mt-4 px-3 pb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Admin
            </p>
            {ADMIN_NAV_ITEMS.map(({ href, label, icon: Icon }) => (
              <NavLink
                key={href}
                href={href}
                label={label}
                icon={Icon}
                active={pathname === href || pathname.startsWith(`${href}/`)}
              />
            ))}
          </>
        ) : null}
      </nav>

      <div className="grid shrink-0 gap-3 pt-6">
        <p className="px-2 text-xs text-muted-foreground">
          <span className="capitalize">{plan}</span> plan ·{" "}
          {formatQuota(usage.watchers_used, usage.watchers_limit)} watchers
        </p>
        <div className="flex items-center gap-2 border-t border-sidebar-border px-2 pt-3">
          <UserButton />
          <span className="text-sm text-muted-foreground">Account</span>
        </div>
      </div>
    </aside>
  );
}

// One sidebar link, shared between the regular and staff-only sections.
function NavLink({
  href,
  label,
  icon: Icon,
  active,
  badge,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  active: boolean;
  badge?: number;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
      )}
    >
      <Icon className="size-4" />
      {label}
      {badge ? <Badge className="ml-auto">{badge}</Badge> : null}
    </Link>
  );
}
