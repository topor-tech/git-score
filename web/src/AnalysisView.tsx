import { useEffect, useState } from "react";
import { createAnalysis, getAnalysis } from "./api";
import ChatPane from "./ChatPane";
import CheckList from "./CheckList";
import RepoPane from "./RepoPane";
import type { Analysis } from "./types";

export default function AnalysisView({
  id,
  onHome,
}: {
  id: string;
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

  async function rerun() {
    if (!analysis) return;
    const created = await createAnalysis(analysis.source);
    window.location.hash = `#/a/${created.id}`;
  }

  const shortSha = analysis?.head_sha ? analysis.head_sha.slice(0, 8) : null;
  const progress = analysis?.progress;
  const statusBits = [];
  if (analysis?.status === "cloning") {
    statusBits.push("cloning");
    if (progress?.percent != null) statusBits.push(`${progress.percent}%`);
    if (progress?.label) statusBits.push(progress.label);
  } else {
    statusBits.push(shortSha ?? "—");
    statusBits.push(analysis?.status ?? "…");
  }

  return (
    <>
      <header className="app-header">
        <button type="button" className="brand" onClick={onHome}>
          Git Score
        </button>
        <div className="header-meta">
          {analysis?.source}
          {statusBits.length ? ` · ${statusBits.join(" · ")}` : ""}
        </div>
        <button type="button" className="ghost" onClick={() => void rerun()} disabled={!analysis}>
          Re-run
        </button>
      </header>
      {error ? <p className="error" style={{ padding: "0 16px" }}>{error}</p> : null}
      {analysis?.status === "failed" ? (
        <p className="error" style={{ padding: "0 16px" }}>
          {analysis.error}
        </p>
      ) : null}
      {analysis ? (
        <div className="workspace">
          <CheckList
            checks={analysis.checks}
            status={analysis.status}
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
