import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">PostPing</h1>
      <p className="max-w-md text-muted-foreground">
        Watch subreddits for the requests you care about. Get notified the moment a matching post
        appears.
      </p>
      <div className="flex gap-3">
        <Button render={<Link href="/sign-up" />}>Get started</Button>
        <Button variant="outline" render={<Link href="/sign-in" />}>
          Sign in
        </Button>
      </div>
    </div>
  );
}
