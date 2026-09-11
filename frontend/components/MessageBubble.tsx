import ReactMarkdown from "react-markdown";
import { isCrisis } from "@/lib/constants";
import type { ChatMessage } from "@/lib/types";
import PathChips from "./PathChips";
import FeedbackRow from "./FeedbackRow";

const USER_AVATAR = "🧑";
const BOT_AVATAR = "🌿";

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const crisis = !isUser && isCrisis(message);

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-black/5 text-base dark:bg-white/10">
        {isUser ? USER_AVATAR : BOT_AVATAR}
      </div>
      <div
        className={`max-w-[85%] rounded-2xl border px-4 py-2.5 text-sm leading-relaxed ${
          crisis
            ? "border-red-300 bg-red-50 text-red-900 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200"
            : isUser
            ? "border-black/10 bg-black/[0.04] dark:border-white/10 dark:bg-white/[0.06]"
            : "border-black/10 bg-[var(--background)] dark:border-white/10"
        }`}
      >
        {crisis && (
          <div className="mb-1 flex items-center gap-1.5 font-semibold">
            🆘 <span>If you&apos;re in crisis</span>
          </div>
        )}
        <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5">
          <ReactMarkdown>{message.text}</ReactMarkdown>
        </div>
        {!isUser && (
          <>
            <PathChips paths={message.pathsUsed} />
            <FeedbackRow logId={message.logId} />
          </>
        )}
      </div>
    </div>
  );
}
