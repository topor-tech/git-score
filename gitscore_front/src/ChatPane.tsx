import { FormEvent, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getMessages, streamChat } from "./api";
import type { ChatMessage, CheckResult } from "./types";

function MessageBody({
  text,
  onPath,
}: {
  text: string;
  onPath: (path: string) => void;
}) {
  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  const re = /\[\[path:([^\]]+)\]\]|\[\[check:([^\]]+)\]\]/g;
  while ((match = re.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[1]) {
      const path = match[1];
      nodes.push(
        <button key={`${path}-${match.index}`} type="button" className="cite" onClick={() => onPath(path)}>
          {path}
        </button>,
      );
    } else if (match[2]) {
      const cid = match[2];
      nodes.push(
        <a key={`${cid}-${match.index}`} className="cite" href={`#/wiki/${cid}`}>
          {cid}
        </a>,
      );
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <>{nodes}</>;
}

export default function ChatPane({
  analysisId,
  ready,
  checks,
  onOpenPath,
}: {
  analysisId: string;
  ready: boolean;
  checks: CheckResult[];
  onOpenPath: (path: string) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState("");
  const [tool, setTool] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ready) return;
    getMessages(analysisId)
      .then((rows) => setMessages(rows.filter((m) => m.role === "user" || m.role === "assistant")))
      .catch(() => setMessages([]));
  }, [analysisId, ready]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [messages, streaming]);

  const suggestions = useMemo(() => {
    return checks
      .filter((c) => c.status === "FAIL" || c.status === "WARN")
      .slice(0, 4)
      .map((c) => `Why did ${c.id} ${c.status === "FAIL" ? "fail" : "warn"}?`);
  }, [checks]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy || !ready) return;
    setBusy(true);
    setError(null);
    setStreaming("");
    setTool(null);
    setMessages((prev) => [
      ...prev,
      {
        id: `local-${Date.now()}`,
        analysis_id: analysisId,
        role: "user",
        content: message,
        created_at: new Date().toISOString(),
      },
    ]);
    setDraft("");
    let acc = "";
    try {
      await streamChat(analysisId, message, (ev) => {
        if (ev.type === "token" && ev.text) {
          acc += ev.text;
          setStreaming(acc);
        }
        if (ev.type === "tool") setTool(ev.name || "tool");
        if (ev.type === "error") setError(ev.message || "chat error");
      });
      if (acc.trim()) {
        setMessages((prev) => [
          ...prev,
          {
            id: `asst-${Date.now()}`,
            analysis_id: analysisId,
            role: "assistant",
            content: acc,
            created_at: new Date().toISOString(),
          },
        ]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "chat failed");
    } finally {
      setStreaming("");
      setTool(null);
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(draft);
  }

  return (
    <section className="pane">
      <div className="pane-title">Chat</div>
      {!ready ? (
        <p className="placeholder">Chat unlocks when every check has finished. There is no overall score.</p>
      ) : (
        <>
          <div className="chat-log" ref={logRef}>
            {messages.map((m) => (
              <div key={m.id} className={`bubble ${m.role}`}>
                <MessageBody text={m.content} onPath={onOpenPath} />
              </div>
            ))}
            {streaming ? (
              <div className="bubble assistant">
                <MessageBody text={streaming} onPath={onOpenPath} />
              </div>
            ) : null}
            {tool ? <div className="tool-note">using {tool}…</div> : null}
            {error ? <p className="error">{error}</p> : null}
          </div>
          {suggestions.length > 0 && !busy ? (
            <div className="suggestions">
              {suggestions.map((s) => (
                <button key={s} type="button" onClick={() => void send(s)}>
                  {s}
                </button>
              ))}
            </div>
          ) : null}
          <form className="composer" onSubmit={onSubmit}>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask about a check, not for an overall score"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(draft);
                }
              }}
            />
            <button className="primary" type="submit" disabled={busy || !draft.trim()}>
              Send
            </button>
          </form>
        </>
      )}
    </section>
  );
}
