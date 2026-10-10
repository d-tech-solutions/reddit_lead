import { PostFeed } from "@/components/post-feed";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { PostPage } from "@/lib/types";

async function loadPosts(
  subreddit: string | null,
): Promise<
  | { ok: true; page: PostPage }
  | { ok: false; status: number | null; message: string }
> {
  try {
    const query = subreddit ? `?${new URLSearchParams({ subreddit }).toString()}` : "";
    const page = await apiFetch<PostPage>(`/posts${query}`);
    return { ok: true, page };
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

export default async function PostsPage({
  searchParams,
}: {
  searchParams: Promise<{ subreddit?: string }>;
}) {
  const { subreddit } = await searchParams;
  const result = await loadPosts(subreddit ?? null);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 p-8">
      <header className="grid gap-1">
        <h1 className="text-2xl font-semibold">Posts</h1>
        <p className="text-sm text-muted-foreground">
          Every post the AI verifier confirmed for at least one watcher, across every subreddit any
          watcher follows, newest first. Posts nobody matched are discarded once judged.
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
      ) : result.page.subreddits.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No watchers yet</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Matched posts show up here once at least one watcher exists somewhere in the app.
          </CardContent>
        </Card>
      ) : (
        <PostFeed
          initialItems={result.page.items}
          initialCursor={result.page.next_cursor}
          subreddits={result.page.subreddits}
          selectedSubreddit={subreddit ?? null}
        />
      )}
    </div>
  );
}
