"use client";

import { useEffect, useState } from "react";
import { checkBackendOnline, fetchThreads } from "@/lib/api";
import { EXAMPLES } from "@/lib/constants";
import type { ThreadSummary } from "@/lib/types";
import ThemeToggle from "./ThemeToggle";

function shortTitle(title: string | null, limit = 34): string {
  const t = title || "Untitled (naming…)";
  return t.length <= limit ? t : t.slice(0, limit - 1).trimEnd() + "…";
}

interface Props {
  deviceId: string;
  currentThreadId: string;
  exchangeCount: number;
  hasMessages: boolean;
  onSelectThread: (id: string) => void;
  onNewConversation: () => void;
  onExample: (question: string) => void;
  open: boolean;
  onClose: () => void;
}

export default function Sidebar({
  deviceId,
  currentThreadId,
  exchangeCount,
  hasMessages,
  onSelectThread,
  onNewConversation,
  onExample,
  open,
  onClose,
}: Props) {
  const [online, setOnline] = useState<boolean | null>(null);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    checkBackendOnline().then((v) => !cancelled && setOnline(v));
    const id = setInterval(() => {
      checkBackendOnline().then((v) => !cancelled && setOnline(v));
    }, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchThreads(deviceId).then((t) => !cancelled && setThreads(t));
    return () => {
      cancelled = true;
    };
    // refetch whenever the active thread changes (a new turn may have just
    // gotten this thread its first generated title)
  }, [deviceId, currentThreadId, exchangeCount]);

  const past = threads.filter((t) => t.thread_id !== currentThreadId);

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-20 bg-black/30 md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-30 w-72 flex-none transform overflow-y-auto border-r border-black/10 bg-[var(--background)] p-4 transition-transform md:static md:z-auto md:translate-x-0 dark:border-white/10 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold">🌿 CBT &amp; Mental Health</h2>
            <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
              Hybrid graph + vector retrieval, corrective-retrieval router,
              memory, web-search fallback.
            </p>
          </div>
          <ThemeToggle />
        </div>

        <div className="mt-3">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
              online === false
                ? "bg-red-500/15 text-red-700 dark:text-red-400"
                : "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
            }`}
          >
            {online === null ? "⏳ Checking…" : online ? "🟢 Ready" : "🔴 Unavailable"}
          </span>
        </div>

        <hr className="my-3 border-black/10 dark:border-white/10" />

        <button
          onClick={onNewConversation}
          className="w-full rounded-lg bg-emerald-700 px-3 py-2 text-left text-sm font-medium text-white transition hover:bg-emerald-800"
        >
          🗑️ New conversation
        </button>

        {past.length > 0 && (
          <div className="mt-4">
            <p className="mb-1.5 text-xs font-semibold text-neutral-500 dark:text-neutral-400">
              Conversations
            </p>
            <div className="flex flex-col gap-1">
              {past.map((t) => (
                <button
                  key={t.thread_id}
                  title={t.title || undefined}
                  onClick={() => onSelectThread(t.thread_id)}
                  className="truncate rounded-lg px-3 py-1.5 text-left text-sm transition hover:bg-black/5 dark:hover:bg-white/10"
                >
                  {shortTitle(t.title)}
                </button>
              ))}
            </div>
          </div>
        )}

        {hasMessages && (
          <div className="mt-4">
            <hr className="mb-3 border-black/10 dark:border-white/10" />
            <p className="mb-1.5 text-xs font-semibold text-neutral-500 dark:text-neutral-400">
              Try an example
            </p>
            <div className="flex flex-col gap-1">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => onExample(ex)}
                  className="truncate rounded-lg px-3 py-1.5 text-left text-sm transition hover:bg-black/5 dark:hover:bg-white/10"
                >
                  💬 {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        <p className="mt-4 text-xs text-neutral-500 dark:text-neutral-400">
          {exchangeCount} exchanges · thread{" "}
          <code className="rounded bg-black/5 px-1 py-0.5 dark:bg-white/10">
            {currentThreadId.slice(0, 8)}
          </code>
        </p>
      </aside>
    </>
  );
}
