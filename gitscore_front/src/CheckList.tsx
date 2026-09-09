import { useMemo, useState } from "react";
import type { CheckResult, GroupBy } from "./types";

const GROUP_ORDER = ["R", "D", "G", "Q", "LT", "S", "L", "T"];
const GROUP_TITLES: Record<string, string> = {
  R: "Git hygiene",
  D: "Docs & ownership",
  G: "Change control",
  Q: "CI & quality",
  LT: "Linting",
  S: "Security",
  L: "Release",
  T: "Team & process",
};

function statusRank(check: CheckResult): number {
  const order: Record<string, number> = {
    FAIL: 0,
    WARN: 1,
    UNKNOWN: 2,
    PASS: 4,
    NOT_APPLICABLE: 5,
  };
  if (check.status == null && check.evaluation_mode === "observation") return 3;
  return order[check.status ?? ""] ?? 3;
}

function Badge({ check }: { check: CheckResult }) {
  if (check.evaluation_mode === "observation" && check.status == null) {
    return <span className="badge obs">OBS</span>;
  }
  const status = (check.status || "UNKNOWN") as string;
  const cls =
    status === "PASS"
      ? "pass"
      : status === "FAIL"
        ? "fail"
        : status === "WARN"
          ? "warn"
          : status === "NOT_APPLICABLE"
            ? "na"
            : "unk";
  const label = status === "NOT_APPLICABLE" ? "N/A" : status;
  return <span className={`badge ${cls}`}>{label}</span>;
}

function EvidenceView({
  check,
  onOpenPath,
}: {
  check: CheckResult;
  onOpenPath: (path: string) => void;
}) {
  const evidence = check.evidence || {};
  const paths = Array.isArray(evidence.paths) ? (evidence.paths as string[]) : [];
  const commits = Array.isArray(evidence.commits)
    ? (evidence.commits as { sha?: string; subject?: string }[])
    : [];
  const authors = evidence.authors;
  const counts =
    evidence.counts && typeof evidence.counts === "object"
      ? (evidence.counts as Record<string, unknown>)
      : null;
  const samples = Array.isArray(evidence.samples) ? evidence.samples : [];

  return (
    <div className="evidence">
      {check.reason_code ? (
        <div className="mono">reason: {check.reason_code}</div>
      ) : null}
      {check.remediation ? <p>{check.remediation}</p> : null}
      {counts
        ? Object.entries(counts).map(([k, v]) => (
            <div key={k} className="mono">
              {k}: {String(v)}
            </div>
          ))
        : null}
      {paths.length > 0 ? (
        <ul>
          {paths.map((p) => (
            <li key={p}>
              <button type="button" className="linkish" onClick={() => onOpenPath(p)}>
                {p}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {commits.length > 0 ? (
        <ul>
          {commits.map((c, i) => (
            <li key={`${c.sha}-${i}`} className="mono">
              {(c.sha || "").slice(0, 8)} {c.subject}
            </li>
          ))}
        </ul>
      ) : null}
      {Array.isArray(authors) ? (
        <ul>
          {authors.map((a, i) => (
            <li key={i} className="mono">
              {typeof a === "string"
                ? a
                : `${(a as { name?: string }).name} (${(a as { commits?: number }).commits ?? ""})`}
            </li>
          ))}
        </ul>
      ) : null}
      {samples.length > 0 ? (
        <ul>
          {samples.slice(0, 12).map((s, i) => (
            <li key={i} className="mono">
              {typeof s === "string" ? s : JSON.stringify(s)}
            </li>
          ))}
        </ul>
      ) : null}
      <a className="wiki-link" href={`#/wiki/${check.id}`}>
        Wiki: {check.id}
      </a>
    </div>
  );
}

function CheckRow({
  check,
  open,
  onToggle,
  onOpenPath,
}: {
  check: CheckResult;
  open: boolean;
  onToggle: () => void;
  onOpenPath: (path: string) => void;
}) {
  return (
    <div>
      <button type="button" className={`check ${open ? "open" : ""}`} onClick={onToggle}>
        <div className="check-top">
          <span className="check-title">
            <span className="check-id">{check.id}</span> {check.title}
          </span>
          <span className="check-meta">
            <span className="prio">{check.importance}/5</span>
            <Badge check={check} />
          </span>
        </div>
        <p className="check-summary">{check.summary}</p>
      </button>
      {open ? <EvidenceView check={check} onOpenPath={onOpenPath} /> : null}
    </div>
  );
}

export default function CheckList({
  checks,
  status,
  groupBy,
  onGroupByChange,
  onOpenPath,
  progressLabel,
  progressPercent,
}: {
  checks: CheckResult[];
  status: string;
  groupBy: GroupBy;
  onGroupByChange: (groupBy: GroupBy) => void;
  onOpenPath: (path: string) => void;
  progressLabel?: string | null;
  progressPercent?: number | null;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const sorted = [...checks].sort((a, b) => {
      const r = statusRank(a) - statusRank(b);
      if (r !== 0) return r;
      return (b.importance || 0) - (a.importance || 0);
    });
    const map = new Map<string, CheckResult[]>();
    if (groupBy === "group") {
      for (const g of GROUP_ORDER) map.set(g, []);
      for (const check of sorted) {
        const key = check.group || check.category || "?";
        const list = map.get(key) ?? [];
        list.push(check);
        map.set(key, list);
      }
    } else {
      for (const n of [5, 4, 3, 2, 1]) map.set(String(n), []);
      for (const check of sorted) {
        const key = String(check.importance || 1);
        const list = map.get(key) ?? [];
        list.push(check);
        map.set(key, list);
      }
    }
    return [...map.entries()].filter(([, list]) => list.length > 0);
  }, [checks, groupBy]);

  function heading(key: string): string {
    if (groupBy === "priority") return `${key}/5 importance`;
    return `${key} · ${GROUP_TITLES[key] || key}`;
  }

  const busy = status === "cloning" || status === "queued" || status === "running_checks";
  const progressText =
    status === "running_checks"
      ? progressLabel
        ? `Running checks… ${progressLabel}`
        : "Running checks…"
      : status === "cloning" || status === "queued"
        ? progressLabel
          ? `Cloning… ${progressLabel}`
          : "Waiting for the working copy…"
        : null;

  return (
    <section className="pane">
      <div className="pane-title">
        Checks
        <span className="status-pill">{status.replace("_", " ")}</span>
      </div>
      <div className="group-toggle">
        <button
          type="button"
          className={groupBy === "group" ? "active" : ""}
          onClick={() => onGroupByChange("group")}
        >
          By group
        </button>
        <button
          type="button"
          className={groupBy === "priority" ? "active" : ""}
          onClick={() => onGroupByChange("priority")}
        >
          By priority
        </button>
      </div>
      <div className="pane-body">
        {busy && progressText ? (
          <p className="placeholder check-progress-label">{progressText}</p>
        ) : checks.length === 0 ? (
          <p className="placeholder">No checks yet.</p>
        ) : null}
        {busy && progressPercent != null ? (
          <div className="meter" style={{ margin: "0 12px 12px" }}>
            <span style={{ width: `${Math.min(100, Math.max(0, progressPercent))}%` }} />
          </div>
        ) : null}
        {grouped.map(([key, list]) => (
          <div key={key} className="check-group">
            <h3>{heading(key)}</h3>
            {list.map((check) => (
              <CheckRow
                key={check.id}
                check={check}
                open={openId === check.id}
                onToggle={() => setOpenId(openId === check.id ? null : check.id)}
                onOpenPath={onOpenPath}
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
