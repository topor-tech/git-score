export type CheckStatus = "PASS" | "WARN" | "FAIL" | "NOT_APPLICABLE" | "UNKNOWN" | null;

export type CheckResult = {
  id: string;
  check_id?: string;
  title: string;
  category: string;
  group: string;
  group_title?: string;
  tags?: string[];
  importance: number;
  evaluation_mode?: "policy" | "observation";
  check_type?: string;
  status: CheckStatus;
  score: number | null;
  summary: string;
  evidence: Record<string, unknown>;
  observations?: Record<string, unknown>;
  evidence_flags?: Record<string, boolean | null>;
  data_quality?: { complete?: boolean; missing_sources?: string[] };
  reason_code?: string | null;
  remediation?: string | null;
  wiki_id?: string;
  /** legacy v1 */
  score_kind?: "binary" | "ratio";
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

export type CatalogCheck = {
  id: string;
  title: string;
  group: string;
  group_title: string;
  group_title_ru?: string;
  tags: string[];
  importance: number;
  importance_label: string;
  evaluation_mode: string;
  check_type: string;
  required_sources: string[];
  interpretation: string;
  implementation: string;
  notes: string;
  definition_version: string;
  group_notes?: string;
  neighbors?: { prev: string | null; next: string | null };
};

export type CatalogGroup = {
  id: string;
  title: string;
  title_ru: string;
  notes: string;
  checks: CatalogCheck[];
};

export type CatalogIndex = {
  title: string;
  source: string;
  intro: string;
  footer: string;
  groups: CatalogGroup[];
  checks: CatalogCheck[];
};
