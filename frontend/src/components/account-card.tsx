"use client";

import { useClerk } from "@clerk/nextjs";
import { LogOut } from "lucide-react";

import { DeleteAccountDialog } from "@/components/delete-account-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Account-level controls: who's signed in, signing out, and deleting the account. Plan details
// live in PlanCard instead.
//
// A Client Component for `useClerk().signOut()` — everything else here is static once rendered.
export function AccountCard({ email }: { email: string | null }) {
  const { signOut } = useClerk();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Account</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {email ? (
          <div className="grid gap-1">
            <span className="text-xs text-muted-foreground">Signed in as</span>
            <span className="text-sm font-medium">{email}</span>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
          <Button variant="outline" onClick={() => signOut({ redirectUrl: "/sign-in" })}>
            <LogOut className="size-4" />
            Log out
          </Button>

          <DeleteAccountDialog>
            <Button variant="destructive">Delete account</Button>
          </DeleteAccountDialog>
        </div>
      </CardContent>
    </Card>
  );
}
