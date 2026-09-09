import hljs from "highlight.js/lib/core";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import python from "highlight.js/lib/languages/python";
import json from "highlight.js/lib/languages/json";
import xml from "highlight.js/lib/languages/xml";
import markdown from "highlight.js/lib/languages/markdown";
import yaml from "highlight.js/lib/languages/yaml";
import bash from "highlight.js/lib/languages/bash";
import "highlight.js/styles/github-dark.css";
import { useEffect, useState } from "react";
import { getFile, getTree } from "./api";
import type { FilePayload, TreeEntry } from "./types";

hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("python", python);
hljs.registerLanguage("json", json);
hljs.registerLanguage("xml", xml);
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("yaml", yaml);
hljs.registerLanguage("bash", bash);

function langFor(path: string): string | undefined {
  const ext = path.split(".").pop()?.toLowerCase();
  const map: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    py: "python",
    json: "json",
    md: "markdown",
    html: "xml",
    xml: "xml",
    yml: "yaml",
    yaml: "yaml",
    sh: "bash",
    css: "css",
  };
  return ext ? map[ext] : undefined;
}

function TreeNode({
  analysisId,
  path,
  name,
  depth,
  selected,
  onSelect,
}: {
  analysisId: string;
  path: string;
  name: string;
  depth: number;
  selected: string | null;
  onSelect: (path: string, kind: "dir" | "file") => void;
}) {
  const [open, setOpen] = useState(path === "");
  const [kids, setKids] = useState<TreeEntry[] | null>(null);

  useEffect(() => {
    if (!open) return;
    getTree(analysisId, path)
      .then((listing) => setKids(listing.entries))
      .catch(() => setKids([]));
  }, [analysisId, path, open]);

  const isSelected = selected === path && path !== "";
  return (
    <div>
      {name ? (
        <button
          type="button"
          className={`tree-row ${isSelected ? "active" : ""}`}
          style={{ paddingLeft: 8 + depth * 12 }}
          onClick={() => {
            setOpen((v) => !v);
            onSelect(path, "dir");
          }}
        >
          {open ? "▾" : "▸"} {name}
        </button>
      ) : null}
      {open && kids
        ? kids.map((entry) => {
            const childPath = path ? `${path}/${entry.name}` : entry.name;
            if (entry.kind === "dir") {
              return (
                <TreeNode
                  key={childPath}
                  analysisId={analysisId}
                  path={childPath}
                  name={entry.name}
                  depth={depth + (name ? 1 : 0)}
                  selected={selected}
                  onSelect={onSelect}
                />
              );
            }
            return (
              <button
                key={childPath}
                type="button"
                className={`tree-row ${selected === childPath ? "active" : ""}`}
                style={{ paddingLeft: 8 + (depth + (name ? 1 : 0)) * 12 }}
                onClick={() => onSelect(childPath, "file")}
              >
                {entry.name}
              </button>
            );
          })
        : null}
    </div>
  );
}

export default function RepoPane({
  analysisId,
  ready,
  selectedPath,
  onSelectPath,
}: {
  analysisId: string;
  ready: boolean;
  selectedPath: string | null;
  onSelectPath: (path: string) => void;
}) {
  const [file, setFile] = useState<FilePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready || !selectedPath) {
      setFile(null);
      return;
    }
    setError(null);
    getFile(analysisId, selectedPath)
      .then(setFile)
      .catch((err) => setError(err instanceof Error ? err.message : "read failed"));
  }, [analysisId, selectedPath, ready]);

  const highlighted =
    file?.kind === "text" && file.content
      ? (() => {
          const lang = langFor(file.path);
          try {
            if (lang && hljs.getLanguage(lang)) {
              return hljs.highlight(file.content, { language: lang }).value;
            }
            return hljs.highlightAuto(file.content).value;
          } catch {
            return null;
          }
        })()
      : null;

  return (
    <section className="pane">
      <div className="pane-title">Repository</div>
      {!ready ? (
        <p className="placeholder">Tree appears once the working copy is ready.</p>
      ) : (
        <div className="repo-split">
          <div className="tree">
            <TreeNode
              analysisId={analysisId}
              path=""
              name=""
              depth={0}
              selected={selectedPath}
              onSelect={(path, kind) => {
                if (kind === "file") onSelectPath(path);
              }}
            />
          </div>
          <div className="viewer">
            {error ? <p className="placeholder">{error}</p> : null}
            {!selectedPath ? <p className="placeholder">Select a file in the tree, or click a path in a check.</p> : null}
            {file ? (
              <>
                <div className="viewer-head">
                  {file.path}
                  {file.truncated ? " · truncated" : ""}
                  {file.kind !== "text" ? ` · ${file.kind}` : ""}
                </div>
                {file.kind === "text" && file.content != null ? (
                  highlighted ? (
                    <pre>
                      <code dangerouslySetInnerHTML={{ __html: highlighted }} />
                    </pre>
                  ) : (
                    <pre>
                      <code>{file.content}</code>
                    </pre>
                  )
                ) : (
                  <p className="placeholder">{file.notice || `Cannot display ${file.kind} file.`}</p>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
