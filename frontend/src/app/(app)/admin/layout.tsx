import { notFound } from "next/navigation";

import { apiFetch } from "@/lib/api";
import type { Me } from "@/lib/types";

// Gates the whole /admin route tree. A 404 rather than a 403 page — a non-admin shouldn't be able
// to tell the route exists at all. The API enforces the real boundary independently
// (`require_superadmin`); this only keeps the UI from being reachable by a non-admin who guesses
// the URL.
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  let me: Me;
  try {
    me = await apiFetch<Me>("/me");
  } catch {
    notFound();
  }

  if (!me.user.is_superadmin) {
    notFound();
  }

  return children;
}
