import { auth } from "@clerk/nextjs/server";
import { UserButton } from "@clerk/nextjs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default async function DashboardPage() {
  const { isAuthenticated, redirectToSignIn } = await auth();

  if (!isAuthenticated) return redirectToSignIn();

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Watchers</h1>
        <UserButton />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>No watchers yet</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Watcher creation and the match feed are not built yet — this page is a placeholder
          proving the auth gate works end to end.
        </CardContent>
      </Card>
    </div>
  );
}
