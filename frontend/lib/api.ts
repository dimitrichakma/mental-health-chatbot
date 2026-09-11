import type { ChatMessage, StreamEvent, ThreadSummary } from "./types";

// Baked in at Docker build time (Railway passes service variables as build
// args - see Dockerfile.frontend). Falls back to a local backend for `npm run dev`.
export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

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

/** The sidebar's past-conversations list for this device. Best-effort - an
 * empty list just means the sidebar section doesn't render. */
export async function fetchThreads(deviceId: string): Promise<ThreadSummary[]> {
  try {
    const res = await fetch(
      `${BACKEND_URL}/threads?device_id=${encodeURIComponent(deviceId)}`,
      { signal: AbortSignal.timeout(5000), cache: "no-store" }
    );
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
      headers: { "Content-Type": "application/json" },
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
  deviceId: string;
  onEvent: (evt: StreamEvent) => void;
  signal?: AbortSignal;
}

/** Streams POST /chat/stream (text/event-stream, `data: {...}\n\n` frames -
 * see backend/backend.py's _sse()) and calls onEvent per parsed frame.
 *
 * This is a real browser->backend fetch (not a server-side relay like the
 * old Streamlit app's `requests.post`), so the backend sees the visitor's
 * actual IP via X-Forwarded-For on its own - no client_ip forwarding hack
 * needed for crisis-helpline geolocation (src/geoip.py) anymore. */
export async function streamChat({
  question,
  threadId,
  deviceId,
  onEvent,
  signal,
}: StreamChatArgs): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      thread_id: threadId,
      device_id: deviceId,
    }),
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
