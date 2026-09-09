export type CheckResult = {
  id: string;
  title: string;
  category: string;
  score: number;
  score_kind: "binary" | "ratio";
  summary: string;
  evidence: Record<string, unknown>;
};

export type Analysis = {
  id: string;
  source_type: "path" | "url";
  source: string;
  working_copy: string | null;
  head_sha: string | null;
  status: "queued" | "cloning" | "running_checks" | "complete" | "failed";
  error: string | null;
  checks: CheckResult[];
  created_at: string;
  completed_at: string | null;
  chat_ready: boolean;
  tree_ready: boolean;
  progress: {
    phase?: string;
    percent?: number;
    current?: number;
    total?: number;
    unit?: string;
    size?: string | null;
    label?: string;
  } | null;
};

export type TreeEntry = {
  name: string;
  kind: "dir" | "file";
  size?: number;
};

export type TreeListing = {
  path: string;
  entries: TreeEntry[];
};

export type FilePayload = {
  path: string;
  kind: "text" | "binary" | "too_large" | "blocked";
  size: number;
  truncated: boolean;
  content: string | null;
  notice?: string;
};

export type ChatMessage = {
  id: string;
  analysis_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  created_at: string;
};
