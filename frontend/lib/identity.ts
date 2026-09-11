// Anonymous per-browser identity - there's no login. device_id groups the
// sidebar's conversation list; thread_id is the active conversation. Both
// live in the URL (?d=&t=) so a bookmark/refresh keeps the same conversation
// instead of silently starting a new one (mirrors the old Streamlit app's
// approach, ported here since Next.js has no server-side session either).

function newId(): string {
  return crypto.randomUUID();
}

export function getOrCreateDeviceId(): string {
  const params = new URLSearchParams(window.location.search);
  let id = params.get("d") || window.localStorage.getItem("device_id");
  if (!id) id = newId();
  window.localStorage.setItem("device_id", id);
  setUrlParam("d", id);
  return id;
}

export function getThreadIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("t");
}

export function setThreadId(id: string) {
  setUrlParam("t", id);
}

export function newThreadId(): string {
  return newId();
}

function setUrlParam(key: string, value: string) {
  const url = new URL(window.location.href);
  url.searchParams.set(key, value);
  window.history.replaceState({}, "", url.toString());
}
