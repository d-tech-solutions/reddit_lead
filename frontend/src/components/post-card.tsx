"use client";

import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { Post } from "@/lib/types";

// One raw ingested post: title, body, and both of its timestamps.
//
// `posted_at` and `fetched_at` are shown side by side rather than collapsed into one "time ago" —
// this is the raw feed, and the gap between "Reddit says this went up" and "we picked it up" is
// exactly the kind of thing someone debugging ingestion lag would open this page to check.
export function PostCard({ post }: { post: Post }) {
  return (
    <Card>
      <CardHeader className="gap-2 space-y-0">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="font-mono">
            r/{post.subreddit}
          </Badge>
          {post.author ? <span>u/{post.author}</span> : null}
          <span className="ml-auto shrink-0" suppressHydrationWarning>
            Fetched{" "}
            <time dateTime={post.fetched_at} title={new Date(post.fetched_at).toLocaleString()}>
              {new Date(post.fetched_at).toLocaleString()}
            </time>
          </span>
        </div>

        <h3 className="text-base leading-snug font-medium">{post.title}</h3>

        {post.posted_at ? (
          <p className="text-xs text-muted-foreground" suppressHydrationWarning>
            Posted{" "}
            <time dateTime={post.posted_at} title={new Date(post.posted_at).toLocaleString()}>
              {new Date(post.posted_at).toLocaleString()}
            </time>
          </p>
        ) : null}
      </CardHeader>

      <CardContent className="grid gap-3 text-sm">
        {post.body ? (
          <p className="line-clamp-4 whitespace-pre-line text-muted-foreground">{post.body}</p>
        ) : null}

        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            render={<a href={post.permalink} target="_blank" rel="noopener noreferrer" />}
          >
            View on Reddit
            <ExternalLink className="size-3.5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
