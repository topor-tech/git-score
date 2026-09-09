import { useMemo, useState } from "react";
import type { CheckResult } from "./types";

const CATEGORY_ORDER = ["hygiene", "activity", "community", "structure", "risk"];

function scoreValue(check: CheckResult): number {
  return check.score_kind === "binary" ? (check.score ? 1 : 0) : check.score;
}

function Badge({ check }: { check: CheckResult }) {
  if (check.score_kind === "binary") {
    const pass = check.score === 1;
    return <span className={`badge ${pass ? "pass" : "fail"}`}>{pass ? "PASS" : "FAIL"}</span>;
  }
  return <span className="badge pass">{Math.round(check.score * 100)}%</span>;
}

function EvidenceView({
  evidence,
  onOpenPath,
}: {
  evidence: Record<string, unknown>;
  onOpenPath: (path: string) => void;
}) {
  const paths = Array.isArray(evidence.paths) ? (evidence.paths as string[]) : [];
  const commits = Array.isArray(evidence.commits) ? (evidence.commits as { sha?: string; subject?: string }[]) : [];
  const authors = evidence.authors;
  const counts = evidence.counts && typeof evidence.counts === "object" ? (evidence.counts as Record<string, unknown>) : null;

  return (
    <div className="evidence">
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
              {typeof a === "string" ? a : `${(a as { name?: string }).name} (${(a as { commits?: number }).commits ?? ""})`}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default function CheckList({
  checks,
  status,
  onOpenPath,
  progressLabel,
  progressPercent,
}: {
  checks: CheckResult[];
  status: string;
  onOpenPath: (path: string) => void;
  progressLabel?: string | null;
  progressPercent?: number | null;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const grouped = useMemo(() => {
    const sorted = [...checks].sort((a, b) => scoreValue(a) - scoreValue(b));
    const map = new Map<string, CheckResult[]>();
    for (const cat of CATEGORY_ORDER) map.set(cat, []);
    for (const check of sorted) {
      const list = map.get(check.category) ?? [];
      list.push(check);
      map.set(check.category, list);
    }
    return [...map.entries()].filter(([, list]) => list.length > 0);
  }, [checks]);

  return (
    <section className="pane">
      <div className="pane-title">
        Checks
        <span className="status-pill">{status.replace("_", " ")}</span>
      </div>
      <div className="pane-body">
        {checks.length === 0 ? (
          <p className="placeholder">
            {status === "cloning" || status === "queued"
              ? progressLabel
                ? `Cloning… ${progressLabel}`
                : "Waiting for the working copy…"
              : "Running checks…"}
          </p>
        ) : null}
        {status === "cloning" && progressPercent != null ? (
          <div className="meter" style={{ margin: "0 12px 12px" }}>
            <span style={{ width: `${progressPercent}%` }} />
          </div>
        ) : null}
        {grouped.map(([category, list]) => (
          <div key={category} className="check-group">
            <h3>{category}</h3>
            {list.map((check) => {
              const open = openId === check.id;
              return (
                <div key={check.id}>
                  <button
                    type="button"
                    className={`check ${open ? "open" : ""}`}
                    onClick={() => setOpenId(open ? null : check.id)}
                  >
                    <div className="check-top">
                      <span className="check-title">{check.title}</span>
                      <Badge check={check} />
                    </div>
                    {check.score_kind === "ratio" ? (
                      <div className="meter">
                        <span style={{ width: `${Math.round(check.score * 100)}%` }} />
                      </div>
                    ) : null}
                    <p className="check-summary">{check.summary}</p>
                  </button>
                  {open ? <EvidenceView evidence={check.evidence} onOpenPath={onOpenPath} /> : null}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}
