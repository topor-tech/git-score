import { useEffect, useState } from "react";
import AnalysisView from "./AnalysisView";
import Landing from "./Landing";

function parseHash(): string | null {
  const h = window.location.hash;
  const m = h.match(/^#\/a\/([^/]+)$/);
  return m ? decodeURIComponent(m[1]) : null;
}

export default function App() {
  const [id, setId] = useState<string | null>(() => parseHash());

  useEffect(() => {
    const onHash = () => setId(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  function open(next: string) {
    window.location.hash = `#/a/${next}`;
    setId(next);
  }

  function home() {
    window.location.hash = "";
    setId(null);
  }

  if (id) return <AnalysisView id={id} onHome={home} />;
  return (
    <>
      <header className="app-header">
        <button type="button" className="brand" onClick={home}>
          Git Score
        </button>
        <span className="header-meta">local demo · git cli checks · no overall score</span>
      </header>
      <Landing onOpen={open} />
    </>
  );
}
