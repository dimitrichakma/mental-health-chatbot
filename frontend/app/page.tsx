"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  getOrCreateDeviceId,
  getThreadIdFromUrl,
  newThreadId,
  setThreadId as persistThreadId,
} from "@/lib/identity";
import { fetchHistory, streamChat } from "@/lib/api";
import { EXAMPLES } from "@/lib/constants";
import type { ChatMessage, StreamEvent } from "@/lib/types";
import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";
import MessageBubble from "@/components/MessageBubble";

export default function Home() {
  const [ready, setReady] = useState(false);
  const [deviceId, setDeviceId] = useState("");
  const [threadId, setThreadIdState] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // identity + restore-from-URL only makes sense client-side (localStorage,
  // window.location) - same reason the old Streamlit app kept this in
  // st.session_state instead of doing it at import time.
  useEffect(() => {
    const d = getOrCreateDeviceId();
    setDeviceId(d);
    const fromUrl = getThreadIdFromUrl();
    const t = fromUrl || newThreadId();
    setThreadIdState(t);
    persistThreadId(t);
    if (fromUrl) {
      fetchHistory(t).then(setMessages).finally(() => setReady(true));
    } else {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  function startNewConversation() {
    const t = newThreadId();
    setThreadIdState(t);
    persistThreadId(t);
    setMessages([]);
    setSidebarOpen(false);
  }

  async function switchThread(id: string) {
    setThreadIdState(id);
    persistThreadId(id);
    setSidebarOpen(false);
    setMessages(await fetchHistory(id));
  }

  async function ask(question: string) {
    if (!question.trim() || sending) return;
    setInput("");
    setSending(true);
    setMessages((prev) => [...prev, { role: "user", text: question }]);

    let answer = "";
    const meta: { kind: string; pathsUsed: string[]; logId: string | null } = {
      kind: "answer",
      pathsUsed: [],
      logId: null,
    };

    // The assistant's bubble is pushed once as a placeholder, then every
    // token/final update below just overwrites that same last element - no
    // other message can land in between, so this is safe without an index
    // or id to track.
    const applyAssistant = (text: string) => {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          text,
          kind: meta.kind,
          pathsUsed: meta.pathsUsed,
          logId: meta.logId,
        };
        return next;
      });
    };

    setMessages((prev) => [
      ...prev,
      { role: "assistant", text: "Thinking through the knowledge base and graph…" },
    ]);

    try {
      await streamChat({
        question,
        threadId,
        deviceId,
        onEvent: (evt: StreamEvent) => {
          if (evt.type === "meta") {
            meta.kind = evt.kind ?? meta.kind;
            if (evt.paths_used) meta.pathsUsed = evt.paths_used as string[];
          } else if (evt.type === "token") {
            answer += evt.text ?? "";
            applyAssistant(answer);
          } else if (evt.type === "done") {
            meta.kind = evt.kind ?? meta.kind;
            if (evt.paths_used) meta.pathsUsed = evt.paths_used as string[];
            meta.logId = evt.log_id ?? null;
          } else if (evt.type === "error") {
            throw new Error(evt.text || "stream error");
          }
        },
      });
    } catch {
      answer =
        answer || "Sorry, the assistant is temporarily unavailable. Please try again.";
    }

    // flush again after the stream ends - the "done" event's kind/log_id can
    // arrive after the last token, so the last applyAssistant() call above
    // may not reflect them yet.
    applyAssistant(answer);
    setSending(false);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    ask(input);
  }

  if (!ready) return null;

  return (
    <div className="flex flex-1">
      <Sidebar
        deviceId={deviceId}
        currentThreadId={threadId}
        exchangeCount={Math.floor(messages.length / 2)}
        hasMessages={messages.length > 0}
        onSelectThread={switchThread}
        onNewConversation={startNewConversation}
        onExample={ask}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 pb-28 pt-4 sm:px-6">
          <div className="mb-1 flex items-center gap-2 md:hidden">
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="Open menu"
              className="rounded-lg p-2 hover:bg-black/5 dark:hover:bg-white/10"
            >
              ☰
            </button>
          </div>

          <Header />

          <div className="flex flex-1 flex-col gap-3">
            {messages.map((m, i) => (
              <MessageBubble key={i} message={m} />
            ))}

            {messages.length === 0 && (
              <div className="px-2 pb-2 pt-6 text-center opacity-90">
                <div className="text-4xl">🌿</div>
                <h3 className="mt-2 text-base font-semibold">
                  What&apos;s on your mind?
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-neutral-500 dark:text-neutral-400">
                  Ask about CBT techniques, mental-health conditions, or
                  coping skills — or try one of these:
                </p>
                <div className="mx-auto mt-4 grid max-w-lg grid-cols-1 gap-2 sm:grid-cols-2">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex}
                      onClick={() => ask(ex)}
                      className="rounded-xl border border-black/10 bg-black/[0.02] px-3 py-2 text-left text-sm transition hover:bg-black/5 dark:border-white/10 dark:bg-white/[0.03] dark:hover:bg-white/10"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="fixed inset-x-0 bottom-0 border-t border-black/10 bg-[var(--background)] px-4 py-3 dark:border-white/10 md:pl-[19rem]"
        >
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  ask(input);
                }
              }}
              maxLength={2000}
              rows={1}
              disabled={sending}
              placeholder="Ask something about mental health or CBT..."
              className="max-h-32 flex-1 resize-none rounded-xl border border-black/10 bg-[var(--background)] px-3 py-2 text-sm outline-none focus:border-emerald-600 disabled:opacity-60 dark:border-white/15"
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="flex-none rounded-xl bg-emerald-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-800 disabled:opacity-40"
            >
              {sending ? "…" : "Send"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
