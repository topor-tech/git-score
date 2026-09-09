import { useEffect, useState } from "react";
import AnalysisView from "./AnalysisView";
import Landing from "./Landing";
import WikiView from "./WikiView";
import type { GroupBy } from "./types";

type Route =
  | { kind: "home" }
  | { kind: "analysis"; id: string; groupBy: GroupBy }
  | { kind: "wiki"; checkId: string | null };

function parseGroupBy(value: string | null): GroupBy {
  return value === "priority" || value === "by_priority" ? "priority" : "group";
}

function analysisHash(id: string, groupBy: GroupBy = "group"): string {
  return `#/a/${encodeURIComponent(id)}?by=${groupBy}`;
}

function parseHash(): Route {
  const h = window.location.hash.replace(/^#/, "") || "/";
  const qIndex = h.indexOf("?");
  const path = (qIndex >= 0 ? h.slice(0, qIndex) : h) || "/";
  const params = new URLSearchParams(qIndex >= 0 ? h.slice(qIndex + 1) : "");
  const wiki = path.match(/^\/wiki(?:\/([A-Za-z]\d{2}))?\/?$/);
  if (wiki) return { kind: "wiki", checkId: wiki[1] ? wiki[1].toUpperCase() : null };
  const analysis = path.match(/^\/a\/([^/]+)$/);
  if (analysis) {
    return {
      kind: "analysis",
      id: decodeURIComponent(analysis[1]),
      groupBy: parseGroupBy(params.get("by")),
    };
  }
  return { kind: "home" };
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => parseHash());

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  function open(next: string) {
    window.location.hash = analysisHash(next);
  }

  function home() {
    window.location.hash = "";
  }

  return (
    <>
      <header className="app-header">
        <button type="button" className="brand" onClick={home}>
          Git Score
        </button>
        {route.kind === "analysis" ? (
          <div className="header-meta" id="analysis-meta" />
        ) : (
          <span className="header-meta">
            {route.kind === "wiki" ? "check wiki" : "local git checks · no overall score"}
          </span>
        )}
        <nav className="header-nav">
          <a href="#/wiki">Wiki</a>
          <button type="button" className="ghost" onClick={home}>
            Analyze
          </button>
        </nav>
      </header>
      {route.kind === "wiki" ? <WikiView checkId={route.checkId} /> : null}
      {route.kind === "analysis" ? (
        <AnalysisView
          id={route.id}
          groupBy={route.groupBy}
          onGroupByChange={(groupBy) => {
            window.location.hash = analysisHash(route.id, groupBy);
          }}
          onHome={home}
        />
      ) : null}
      {route.kind === "home" ? <Landing onOpen={open} /> : null}
    </>
  );
}
