import { FormEvent, useEffect, useState } from "react";
import { createAnalysis, listAnalyses } from "./api";
import type { Analysis } from "./types";

type Props = {
  onOpen: (id: string) => void;
};

export default function Landing({ onOpen }: Props) {
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<Analysis[]>([]);

  useEffect(() => {
    listAnalyses()
      .then(setRecent)
      .catch(() => setRecent([]));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const created = await createAnalysis(source.trim());
      onOpen(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="landing">
      <h1>Git Score</h1>
      <p className="lede">
        Point at a git repo. Git Score runs the catalog of independent health checks
        (PASS / WARN / FAIL / UNKNOWN, plus observations), lets you browse the tree,
        and explains findings. No overall score. Read every check in the{" "}
        <a href="#/wiki">wiki</a>.
      </p>
      <form className="form-row" onSubmit={onSubmit}>
        <input
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="Local path or clone URL"
          spellCheck={false}
        />
        <button className="primary" type="submit" disabled={busy || !source.trim()}>
          {busy ? "Starting…" : "Analyze"}
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      {recent.length > 0 ? (
        <section className="recent">
          <h2>Recent analyses</h2>
          {recent.map((item) => (
            <button key={item.id} className="recent-item" type="button" onClick={() => onOpen(item.id)}>
              <strong>{item.source}</strong>
              <span>
                {item.status}
                {item.head_sha ? ` · ${item.head_sha.slice(0, 8)}` : ""}
              </span>
            </button>
          ))}
        </section>
      ) : null}
    </div>
  );
}
