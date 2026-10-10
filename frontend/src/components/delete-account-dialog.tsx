"use client";

import { useState, useTransition } from "react";
import { useClerk } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { deleteAccountAction } from "@/app/actions/account";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

// Deletes the account everywhere it exists (Stripe, Clerk, and the local row), then signs out.
//
// A Client Component because signing the browser out is Clerk-client-only — the Server Action can
// delete the account, but only `useClerk().signOut()` can clear the session it was deleted with.
export function DeleteAccountDialog({ children }: { children: React.ReactElement }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const { signOut } = useClerk();
  const router = useRouter();

  function confirmDelete() {
    setError(null);
    startTransition(async () => {
      const result = await deleteAccountAction();
      if (result.error) {
        setError(result.error);
        return;
      }
      try {
        await signOut({ redirectUrl: "/sign-in" });
      } catch {
        // The account (and its Clerk session) is already gone server-side — get the user to the
        // sign-in page either way.
        router.push("/sign-in");
      }
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={children} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete account</DialogTitle>
          <DialogDescription>
            This permanently deletes your account, watchers, matches, and billing history. This
            can&apos;t be undone.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setOpen(false)} disabled={pending}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={confirmDelete} disabled={pending}>
            {pending ? "Deleting…" : "Delete account"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
