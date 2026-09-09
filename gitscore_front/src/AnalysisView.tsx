import { useEffect, useState } from "react";
import { createAnalysis, getAnalysis } from "./api";
import ChatPane from "./ChatPane";
import CheckList from "./CheckList";
import RepoPane from "./RepoPane";
import type { Analysis, GroupBy } from "./types";

function shortError(message: string | null): string {
  if (!message) return "analysis failed";
  if (!/Receiving objects|Resolving deltas|Checking out files|Compressing objects/i.test(message)) {
    return message;
  }
  const warning = message.match(/warning:.*?(?:checkout failed.*?(?:git restore[^\n]*)?)/i);
  if (warning) return warning[0].replace(/\s+/g, " ").trim();
  const lines = message
    .split(/[\r\n]+/)
    .map((line) => line.trim())
    .filter((line) => line && !/\d+%\s+\(\d+\/\d+\)/.test(line));
  return lines.at(-1) || "Clone finished, but the working tree could not be checked out.";
}

export default function AnalysisView({
  id,
  groupBy,
  onGroupByChange,
  onHome,
}: {
  id: string;
  groupBy: GroupBy;
  onGroupByChange: (groupBy: GroupBy) => void;
  onHome: () => void;
}) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const data = await getAnalysis(id);
        if (!cancelled) setAnalysis(data);
        return data.status;
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "load failed");
        return "failed";
      }
    }
    void tick();
    const handle = window.setInterval(async () => {
      const status = await tick();
      if (status === "complete" || status === "failed") {
        window.clearInterval(handle);
      }
    }, 400);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [id]);

  useEffect(() => {
    const el = document.getElementById("analysis-meta");
    if (!el) return;
    const shortSha = analysis?.head_sha ? analysis.head_sha.slice(0, 8) : null;
    const progress = analysis?.progress;
    const bits: string[] = [];
    if (analysis?.status === "cloning") {
      bits.push("cloning");
      if (progress?.percent != null) bits.push(`${progress.percent}%`);
      if (progress?.label) bits.push(progress.label);
    } else if (analysis?.status === "running_checks") {
      bits.push(shortSha ?? "—");
      bits.push(progress?.label || "running checks");
    } else {
      bits.push(shortSha ?? "—");
      bits.push(analysis?.status ?? "…");
    }
    el.textContent = `${analysis?.source ?? ""}${bits.length ? ` · ${bits.join(" · ")}` : ""}`;
  }, [analysis]);

  async function rerun() {
    if (!analysis) return;
    const created = await createAnalysis(analysis.source);
    window.location.hash = `#/a/${created.id}?by=${groupBy}`;
  }

  return (
    <>
      <div className="analysis-toolbar">
        <button type="button" className="ghost" onClick={onHome}>
          Home
        </button>
        <a className="ghost-link" href="#/wiki">
          Check wiki
        </a>
        <button type="button" className="ghost" onClick={() => void rerun()} disabled={!analysis}>
          Re-run
        </button>
      </div>
      {error ? <p className="error" style={{ padding: "0 16px" }}>{error}</p> : null}
      {analysis?.status === "failed" ? (
        <p className="error" style={{ padding: "0 16px" }}>
          {shortError(analysis.error)}
        </p>
      ) : null}
      {analysis ? (
        <div className="workspace">
          <CheckList
            checks={analysis.checks}
            status={analysis.status}
            groupBy={groupBy}
            onGroupByChange={onGroupByChange}
            onOpenPath={setSelectedPath}
            progressLabel={analysis.progress?.label}
            progressPercent={analysis.progress?.percent}
          />
          <RepoPane
            analysisId={id}
            ready={analysis.tree_ready}
            selectedPath={selectedPath}
            onSelectPath={setSelectedPath}
          />
          <ChatPane
            analysisId={id}
            ready={analysis.chat_ready}
            checks={analysis.checks}
            onOpenPath={setSelectedPath}
          />
        </div>
      ) : (
        <p className="placeholder">Loading analysis…</p>
      )}
    </>
  );
}
