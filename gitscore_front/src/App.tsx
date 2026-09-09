import { useEffect, useState } from "react";
import AnalysisView from "./AnalysisView";
import Landing from "./Landing";
import WikiView from "./WikiView";

type Route =
  | { kind: "home" }
  | { kind: "analysis"; id: string }
  | { kind: "wiki"; checkId: string | null };

function parseHash(): Route {
  const h = window.location.hash.replace(/^#/, "") || "/";
  const wiki = h.match(/^\/wiki(?:\/([A-Za-z]\d{2}))?\/?$/);
  if (wiki) return { kind: "wiki", checkId: wiki[1] ? wiki[1].toUpperCase() : null };
  const analysis = h.match(/^\/a\/([^/]+)$/);
  if (analysis) return { kind: "analysis", id: decodeURIComponent(analysis[1]) };
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
    window.location.hash = `#/a/${next}`;
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
      {route.kind === "analysis" ? <AnalysisView id={route.id} onHome={home} /> : null}
      {route.kind === "home" ? <Landing onOpen={open} /> : null}
    </>
  );
}
