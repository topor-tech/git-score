import { useEffect, useMemo, useState, type ReactNode } from "react";
import { getCatalog, getCatalogCheck } from "./api";
import type { CatalogCheck, CatalogIndex } from "./types";

function mdInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[1] && match[2]) {
      const href = match[2];
      const internal = href.match(/^([A-Z]+\d{2})$/i);
      if (internal) {
        nodes.push(
          <a key={match.index} href={`#/wiki/${internal[1].toUpperCase()}`}>
            {match[1]}
          </a>,
        );
      } else {
        nodes.push(
          <a key={match.index} href={href} target="_blank" rel="noreferrer">
            {match[1]}
          </a>,
        );
      }
    } else if (match[3]) {
      nodes.push(<code key={match.index}>{match[3]}</code>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function MdBlock({ text }: { text: string }) {
  if (!text.trim()) return null;
  return (
    <div className="wiki-prose">
      {text.split(/\n\n+/).map((para, i) => (
        <p key={i}>{mdInline(para.replace(/\n/g, " "))}</p>
      ))}
    </div>
  );
}

function WikiIndex({ data }: { data: CatalogIndex }) {
  return (
    <article className="wiki-article">
      <h1>Check wiki</h1>
      <p className="lede">
        Catalog from <code>{data.source}</code>. Importance is the default internal
        production rating (5/5 highest), not an automatic merge blocker.
      </p>
      <MdBlock text={data.intro.replace(/^#.*\n/, "")} />
      {data.groups.map((g) => (
        <section key={g.id} className="wiki-group">
          <h2>
            {g.id}. {g.title_ru || g.title}
          </h2>
          <p className="wiki-sub">{g.title}</p>
          <table className="wiki-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Check</th>
                <th>Importance</th>
              </tr>
            </thead>
            <tbody>
              {g.checks.map((c) => (
                <tr key={c.id}>
                  <td>
                    <a href={`#/wiki/${c.id}`}>{c.id}</a>
                  </td>
                  <td>
                    <a href={`#/wiki/${c.id}`}>{c.title}</a>
                  </td>
                  <td className="mono">{c.importance_label || `${c.importance}/5`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <MdBlock text={g.notes} />
        </section>
      ))}
      <MdBlock text={data.footer} />
    </article>
  );
}

function WikiDetail({
  page,
}: {
  page: CatalogCheck;
}) {
  return (
    <article className="wiki-article">
      <p className="wiki-crumb">
        <a href="#/wiki">All checks</a>
        {page.neighbors?.prev ? (
          <>
            {" · "}
            <a href={`#/wiki/${page.neighbors.prev}`}>{page.neighbors.prev}</a>
          </>
        ) : null}
        {page.neighbors?.next ? (
          <>
            {" · "}
            <a href={`#/wiki/${page.neighbors.next}`}>{page.neighbors.next}</a>
          </>
        ) : null}
      </p>
      <h1>
        <span className="check-id">{page.id}</span> {page.title}
      </h1>
      <p className="wiki-meta">
        {page.group}. {page.group_title_ru || page.group_title} · {page.importance_label} ·{" "}
        {page.evaluation_mode} · {page.check_type}
      </p>
      {page.tags?.length ? (
        <p className="wiki-tags">{page.tags.join(" · ")}</p>
      ) : null}
      <h2>What to check</h2>
      <p>{mdInline(page.interpretation)}</p>
      <h2>Evidence</h2>
      <p>{mdInline(page.implementation)}</p>
      <h2>Sources</h2>
      <p className="mono">{(page.required_sources || []).join(", ") || "—"}</p>
      {page.group_notes ? (
        <>
          <h2>Group notes</h2>
          <MdBlock text={page.group_notes} />
        </>
      ) : null}
    </article>
  );
}

export default function WikiView({ checkId }: { checkId?: string | null }) {
  const [index, setIndex] = useState<CatalogIndex | null>(null);
  const [page, setPage] = useState<CatalogCheck | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCatalog()
      .then(setIndex)
      .catch((err) => setError(err instanceof Error ? err.message : "catalog failed"));
  }, []);

  useEffect(() => {
    if (!checkId) {
      setPage(null);
      return;
    }
    getCatalogCheck(checkId)
      .then(setPage)
      .catch((err) => setError(err instanceof Error ? err.message : "check failed"));
  }, [checkId]);

  const nav = useMemo(() => index?.groups ?? [], [index]);

  return (
    <div className="wiki-layout">
      <nav className="wiki-nav">
        <a className={!checkId ? "active" : ""} href="#/wiki">
          Catalog
        </a>
        {nav.map((g) => (
          <div key={g.id}>
            <div className="wiki-nav-group">
              {g.id} {g.title}
            </div>
            {g.checks.map((c) => (
              <a
                key={c.id}
                href={`#/wiki/${c.id}`}
                className={checkId === c.id ? "active" : ""}
              >
                {c.id} {c.title}
              </a>
            ))}
          </div>
        ))}
      </nav>
      <div className="wiki-main">
        {error ? <p className="error">{error}</p> : null}
        {checkId && page ? <WikiDetail page={page} /> : null}
        {!checkId && index ? <WikiIndex data={index} /> : null}
        {!index && !error ? <p className="placeholder">Loading wiki…</p> : null}
      </div>
    </div>
  );
}
