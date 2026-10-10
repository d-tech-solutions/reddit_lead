"use client";

import { useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { WatcherForm } from "@/components/watcher-form";

// The "New watcher" flow, launched from the sidebar or the watchers page's empty-slot card.
// Both triggers share one dialog instance's worth of behavior via this wrapper rather than each
// managing their own open state and re-implementing "close on successful create".
export function CreateWatcherDialog({ children }: { children: React.ReactElement }) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={children} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New watcher</DialogTitle>
          <DialogDescription>
            PostPing will watch these subreddits and notify you when a post matches.
          </DialogDescription>
        </DialogHeader>
        <WatcherForm onSuccess={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  );
}
