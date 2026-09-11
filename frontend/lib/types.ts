export type Role = "user" | "assistant";

export type Kind = "answer" | "crisis" | "off_topic" | "no_answer" | string;

export type PathUsed =
  | "naive_rag"
  | "graph_rag"
  | "both"
  | "web_fallback"
  | "no_answer"
  | string;

export interface ChatMessage {
  role: Role;
  text: string;
  kind?: Kind | null;
  pathsUsed?: PathUsed[];
  logId?: string | null;
}

export interface ThreadSummary {
  thread_id: string;
  title: string | null;
  updated_at?: string;
}

export interface StreamEvent {
  type: "meta" | "token" | "done" | "error";
  kind?: Kind;
  text?: string;
  paths_used?: PathUsed[];
  log_id?: string | null;
  thread_id?: string;
}
