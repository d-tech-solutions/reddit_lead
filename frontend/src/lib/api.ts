import "server-only";

import { auth } from "@clerk/nextjs/server";

// Server-side base URL. Inside docker-compose the API is reachable as `api`, not `localhost`, so
// this is deliberately NOT the NEXT_PUBLIC_ variable — that one is baked into the browser bundle
// and would point at the wrong host from inside the container.
const API_BASE_URL =
  process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API_V1_PREFIX = "/api/v1";

// Thrown for any non-2xx response, carrying the status so callers can tell a 409 (plan limit,
// worth showing the user) from a 500 (worth logging).
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Pull the detail string out of FastAPI's error body, falling back to the status text.
// FastAPI returns `{detail: "..."}` for HTTPException and `{detail: [...]}` for validation errors.
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      const first = body.detail[0];
      return first?.msg ? `${first.msg}${first.loc ? ` (${first.loc.join(".")})` : ""}` : "Invalid request";
    }
  } catch {
    // Body was not JSON — fall through to the status line.
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

// Call the PostPing API as the signed-in user.
//
// Server-only on purpose: the Clerk session token is attached here and must never reach the
// browser bundle. Keeping every call server-side also means the browser never talks to the API
// directly, so CORS never enters the picture.
//
// Note on caching: in Next 16 `fetch` is uncached by default, so per-user responses are not
// shared between users. Do not add `use cache` to anything on this path.
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { getToken } = await auth();
  const token = await getToken();

  if (!token) {
    throw new ApiError(401, "Not signed in");
  }

  const response = await fetch(`${API_BASE_URL}${API_V1_PREFIX}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }

  // 204 No Content has no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
