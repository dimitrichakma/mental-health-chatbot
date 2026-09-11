"use client";

import { useState } from "react";
import { sendFeedback } from "@/lib/api";

/** Thumbs + optional note under an assistant message. No-op if the backend
 * didn't return a log_id (e.g. logging disabled) - same rule as the old
 * Streamlit UI. */
export default function FeedbackRow({ logId }: { logId?: string | null }) {
  const [sent, setSent] = useState<number | null>(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const [noteSent, setNoteSent] = useState(false);

  if (!logId) return null;

  async function rate(value: 1 | -1) {
    if (!logId || sent === value) return;
    setSent(value);
    await sendFeedback(logId, { rating: value });
  }

  async function submitNote() {
    if (!logId || !note.trim()) return;
    await sendFeedback(logId, { note: note.trim() });
    setNoteSent(true);
    setTimeout(() => setNoteOpen(false), 900);
  }

  return (
    <div className="mt-2 flex items-center gap-1 text-sm">
      <button
        onClick={() => rate(1)}
        aria-label="Helpful"
        className={`rounded-md px-1.5 py-0.5 transition hover:bg-black/5 dark:hover:bg-white/10 ${
          sent === 1 ? "opacity-100" : "opacity-50"
        }`}
      >
        👍
      </button>
      <button
        onClick={() => rate(-1)}
        aria-label="Not helpful"
        className={`rounded-md px-1.5 py-0.5 transition hover:bg-black/5 dark:hover:bg-white/10 ${
          sent === -1 ? "opacity-100" : "opacity-50"
        }`}
      >
        👎
      </button>
      <div className="relative">
        <button
          onClick={() => setNoteOpen((o) => !o)}
          aria-label="Add a note"
          className="rounded-md px-1.5 py-0.5 opacity-50 transition hover:bg-black/5 hover:opacity-100 dark:hover:bg-white/10"
        >
          💬
        </button>
        {noteOpen && (
          <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-lg border border-black/10 bg-[var(--background)] p-2 shadow-lg dark:border-white/10">
            {noteSent ? (
              <p className="text-xs text-emerald-600 dark:text-emerald-400">
                Note saved — thanks!
              </p>
            ) : (
              <>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Optional: accuracy issue, tone, missing info, safety concern…"
                  rows={3}
                  className="w-full resize-none rounded-md border border-black/10 bg-transparent p-1.5 text-xs outline-none focus:border-emerald-600 dark:border-white/15"
                />
                <button
                  onClick={submitNote}
                  disabled={!note.trim()}
                  className="mt-1.5 w-full rounded-md bg-emerald-700 py-1 text-xs font-medium text-white disabled:opacity-40"
                >
                  Send note
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
