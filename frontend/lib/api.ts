import type { ChatMessage, StreamEvent, ThreadSummary } from "./types";

// Baked in at Docker build time (Railway passes service variables as build
// args - see Dockerfile.frontend). Falls back to a local backend for `npm run dev`.
export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

// --- auth: short-lived backend token ---
// GET /api/backend-token (route.ts) verifies the NextAuth session
// server-side and mints a 10-min HS256 token the backend can verify on its
// own (see src/auth.py). Cached here and refreshed a bit before it expires
// so most calls don't pay the extra round trip.
let cachedToken: { value: string; expiresAt: number } | null = null;

async function getAuthToken(): Promise<string | null> {
  if (cachedToken && cachedToken.expiresAt > Date.now()) {
    return cachedToken.value;
  }
  try {
    const res = await fetch("/api/backend-token", { cache: "no-store" });
    if (!res.ok) return null;
    const { token } = await res.json();
    cachedToken = { value: token, expiresAt: Date.now() + 8 * 60 * 1000 }; // refresh 2 min early
    return token;
  } catch {
    return null;
  }
}

/** Call after sign-out so a stale token can never leak into the next session
 * sharing this tab/module state. */
export function clearAuthToken() {
  cachedToken = null;
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function checkBackendOnline(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, {
      signal: AbortSignal.timeout(3000),
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Restore a conversation from the backend's LangGraph checkpoint (Postgres)
 * after a page refresh / lost session wipes browser-side state. Only text
 * survives server-side (no paths_used/log_id per turn), so restored assistant
 * messages come back without source chips or feedback buttons. */
export async function fetchHistory(threadId: string): Promise<ChatMessage[]> {
  try {
    const res = await fetch(`${BACKEND_URL}/history/${threadId}`, {
      headers: await authHeaders(),
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });
    if (!res.ok) return [];
    const data = await res.json();
    const restored: ChatMessage[] = [];
    for (const turn of data.chat_history ?? []) {
      restored.push({ role: "user", text: turn.question });
      restored.push({
        role: "assistant",
        text: turn.answer,
        pathsUsed: [],
        kind: null,
        logId: null,
      });
    }
    return restored;
  } catch {
    return [];
  }
}

/** The sidebar's past-conversations list for the signed-in user. Best-effort
 * - an empty list just means the sidebar section doesn't render. */
export async function fetchThreads(): Promise<ThreadSummary[]> {
  try {
    const res = await fetch(`${BACKEND_URL}/threads`, {
      headers: await authHeaders(),
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.threads ?? [];
  } catch {
    return [];
  }
}

export async function sendFeedback(
  logId: string,
  opts: { rating?: number; note?: string }
): Promise<void> {
  try {
    await fetch(`${BACKEND_URL}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify({ log_id: logId, ...opts }),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    // best-effort, same as the old Streamlit UI
  }
}

interface StreamChatArgs {
  question: string;
  threadId: string;
  onEvent: (evt: StreamEvent) => void;
  signal?: AbortSignal;
}

/** Streams POST /chat/stream (text/event-stream, `data: {...}\n\n` frames -
 * see backend/backend.py's _sse()) and calls onEvent per parsed frame.
 *
 * This is a real browser->backend fetch (not a server-side relay), so the
 * backend sees the visitor's actual IP via X-Forwarded-For on its own - no
 * client_ip forwarding needed for crisis-helpline geolocation
 * (src/geoip.py). Identity instead comes from the Authorization header. */
export async function streamChat({
  question,
  threadId,
  onEvent,
  signal,
}: StreamChatArgs): Promise<void> {
  const token = await getAuthToken();
  if (!token) throw new Error("not signed in");

  const res = await fetch(`${BACKEND_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question, thread_id: threadId }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`stream request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (!frame.startsWith("data: ")) continue;
      try {
        onEvent(JSON.parse(frame.slice(6)) as StreamEvent);
      } catch {
        // malformed frame - skip rather than abort the whole stream
      }
    }
  }
}
