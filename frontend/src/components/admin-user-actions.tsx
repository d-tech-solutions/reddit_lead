"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  deleteUserAction,
  setUserActiveAction,
  updateUserPlanAction,
} from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { PLAN_LABELS } from "@/lib/plan";
import type { AdminUser } from "@/lib/types";

// Plan select, active/deactivate switch, and a delete-with-confirm dialog for one user — shared
// between the admin user list and the user detail page.
//
// A Client Component because every control here mutates state and needs pending/error feedback;
// the mutations themselves stay Server Actions, so the Clerk token never reaches the browser.
export function AdminUserActions({
  user,
  redirectOnDeleteTo,
}: {
  user: AdminUser;
  // A plain path rather than a callback: this is a Client Component rendered from a Server
  // Component page, so props have to be serializable. The detail page has nowhere to refresh back
  // to once its own subject is deleted, so it passes "/admin" here; the list page omits it and
  // just re-fetches the list in place.
  redirectOnDeleteTo?: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  function run(action: () => Promise<{ error: string | null }>) {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (result.error) {
        setError(result.error);
      }
    });
  }

  function confirmDelete() {
    setError(null);
    startTransition(async () => {
      const result = await deleteUserAction(user.id);
      if (result.error) {
        setError(result.error);
        return;
      }
      setDeleteOpen(false);
      if (redirectOnDeleteTo) {
        router.push(redirectOnDeleteTo);
      } else {
        router.refresh();
      }
    });
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select
        value={user.plan}
        onValueChange={(value) => {
          if (value) run(() => updateUserPlanAction(user.id, value));
        }}
      >
        <SelectTrigger size="sm" disabled={pending}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(PLAN_LABELS).map(([id, label]) => (
            <SelectItem key={id} value={id}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex items-center gap-1.5">
        <Switch
          checked={user.is_active}
          disabled={pending}
          onCheckedChange={(checked) => run(() => setUserActiveAction(user.id, checked))}
        />
        <span className="text-xs text-muted-foreground">
          {user.is_active ? "Active" : "Deactivated"}
        </span>
      </div>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogTrigger render={<Button variant="ghost" size="sm" className="text-destructive" />}>
          Delete
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {user.email ?? "this user"}?</DialogTitle>
            <DialogDescription>
              This permanently deletes their account, watchers, matches, and billing history. This
              can&apos;t be undone.
            </DialogDescription>
          </DialogHeader>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleteOpen(false)} disabled={pending}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={pending}>
              {pending ? "Deleting…" : "Delete user"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {error ? (
        <p role="alert" className="w-full text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
