import type { Analysis, CatalogCheck, CatalogIndex, ChatMessage, FilePayload, TreeListing } from "./types";

async function parse<T>(res: Response | Promise<Response>): Promise<T> {
  const resolved = await res;
  if (!resolved.ok) {
    let detail: unknown = resolved.statusText;
    try {
      const body = await resolved.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      try {
        detail = await resolved.text();
      } catch {
        /* ignore */
      }
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return resolved.json() as Promise<T>;
}

export function createAnalysis(source: string) {
  return parse<Analysis>(
    fetch("/api/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    }),
  );
}

export function listAnalyses() {
  return parse<Analysis[]>(fetch("/api/analyses"));
}

export function getAnalysis(id: string) {
  return parse<Analysis>(fetch(`/api/analyses/${id}`));
}

export function getTree(id: string, path: string) {
  const q = new URLSearchParams({ path });
  return parse<TreeListing>(fetch(`/api/analyses/${id}/tree?${q}`));
}

export function getFile(id: string, path: string) {
  const q = new URLSearchParams({ path });
  return parse<FilePayload>(fetch(`/api/analyses/${id}/file?${q}`));
}

export function getCatalog() {
  return parse<CatalogIndex>(fetch("/api/catalog"));
}

export function getCatalogCheck(id: string) {
  return parse<CatalogCheck>(fetch(`/api/catalog/${encodeURIComponent(id)}`));
}

export function getMessages(id: string) {
  return parse<ChatMessage[]>(fetch(`/api/analyses/${id}/messages`));
}

export async function streamChat(
  id: string,
  message: string,
  onEvent: (ev: { type: string; text?: string; name?: string; message?: string }) => void,
): Promise<void> {
  const res = await fetch(`/api/analyses/${id}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : "chat failed");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const chunks = buf.split("\n\n");
    buf = chunks.pop() ?? "";
    for (const block of chunks) {
      for (const line of block.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (!data) continue;
        try {
          onEvent(JSON.parse(data));
        } catch {
          /* ignore partial json */
        }
      }
    }
  }
}
