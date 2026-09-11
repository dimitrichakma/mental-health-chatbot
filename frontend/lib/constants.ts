import type { ChatMessage, PathUsed } from "./types";

export const PATH_LABELS: Record<string, { icon: string; label: string }> = {
  naive_rag: { icon: "📚", label: "knowledge base" },
  graph_rag: { icon: "🕸️", label: "concept graph" },
  both: { icon: "🔗", label: "knowledge base + graph" },
  web_fallback: { icon: "🌐", label: "web search" },
  no_answer: { icon: "❓", label: "no source found" },
};

export function pathLabel(p: PathUsed) {
  return PATH_LABELS[p] ?? { icon: "", label: p };
}

export const EXAMPLES = [
  "What is cognitive restructuring?",
  "What cognitive distortions does CBT target?",
  "How is panic disorder treated?",
  "What is exposure and response prevention?",
  "How does behavioral activation help with depression?",
];

/** Prefer the backend's explicit kind; fall back to a text heuristic for
 * history restored from the server (/history doesn't carry kind) or saved
 * before the flag existed. The two phrases below are in every crisis
 * response regardless of country (see src/crisis_resources.py), unlike the
 * word "crisis" itself which isn't in every country's helpline list. */
export function isCrisis(message: ChatMessage): boolean {
  if (message.kind) return message.kind === "crisis";
  const answer = message.text.toLowerCase();
  return (
    answer.includes("you don't have to handle this alone") &&
    answer.includes("emergency number")
  );
}
