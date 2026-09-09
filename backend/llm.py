from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import httpx

from . import git_cli
from .config import (
    CONTRIBUTOR_CAP,
    GIT_LOG_CAP,
    LLM_FILE_BYTES,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    SEARCH_HIT_CAP,
    TOOL_ROUND_CAP,
)
from .files import list_dir, read_file_for_llm, search_files

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_checks",
            "description": "Return the full list of check results for this analysis.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_check_evidence",
            "description": "Return summary and evidence for one check id.",
            "parameters": {
                "type": "object",
                "properties": {"check_id": {"type": "string"}},
                "required": ["check_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_contributors",
            "description": "Authors with commit counts and last activity from HEAD history.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List a directory in the working copy (hidden/generated dirs omitted).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Repo-relative directory, empty for root."}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search file paths by substring.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a small text file. Credential-like paths are blocked. Secrets in lines are redacted.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Recent commits on HEAD, optionally filtered by path or author substring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "author": {"type": "string"},
                },
            },
        },
    },
]


def llm_configured() -> bool:
    if not OPENAI_MODEL or not OPENAI_BASE_URL:
        return False
    local = any(h in OPENAI_BASE_URL for h in ("localhost", "127.0.0.1", "::1"))
    return bool(OPENAI_API_KEY) or local


def system_prompt(analysis: dict, checks: list[dict]) -> str:
    summary = {
        "source": analysis.get("source"),
        "head_sha": analysis.get("head_sha"),
        "status": analysis.get("status"),
        "check_count": len(checks),
    }
    return f"""You are Git Score, a local assistant for one analyzed git repository.

v1 does not compute an overall or weighted score. Talk about individual checks only.
Never invent or change check scores. If asked to change a score, refuse and say the user can edit the repo and re-run.
If asked for an overall score, say v1 does not compute one.

Cite files as [[path:relative/path]] and checks as [[check:check_id]].
Do not dump secrets. Do not request credential file contents.

Repo summary: {json.dumps(summary)}
Checks JSON: {json.dumps(checks)}
"""


def execute_tool(name: str, args: dict, *, root: Path, checks: list[dict]) -> Any:
    if name == "get_checks":
        return checks
    if name == "get_check_evidence":
        cid = args.get("check_id")
        for item in checks:
            if item.get("id") == cid:
                return {"id": cid, "summary": item.get("summary"), "evidence": item.get("evidence")}
        return {"error": f"unknown check_id {cid}"}
    if name == "list_contributors":
        commits = git_cli.commit_log(root, 2000)
        stats: dict[str, dict] = {}
        for c in commits:
            key = c["email"] or c["name"] or "unknown"
            slot = stats.setdefault(key, {"name": c["name"], "email": c["email"], "commits": 0, "last_timestamp": 0})
            slot["commits"] += 1
            slot["last_timestamp"] = max(slot["last_timestamp"], c["timestamp"])
        ranked = sorted(stats.values(), key=lambda x: x["commits"], reverse=True)
        return ranked[:CONTRIBUTOR_CAP]
    if name == "list_dir":
        return list_dir(root, args.get("path") or "")
    if name == "search_files":
        return search_files(root, str(args.get("query") or ""), SEARCH_HIT_CAP)
    if name == "read_file":
        return read_file_for_llm(root, str(args.get("path") or ""))
    if name == "git_log":
        commits = git_cli.commit_log(root, 2000)
        path_f = (args.get("path") or "").replace("\\", "/").strip()
        author_f = (args.get("author") or "").lower().strip()
        out = []
        for c in commits:
            if author_f and author_f not in (c["name"] or "").lower() and author_f not in (c["email"] or "").lower():
                continue
            out.append(
                {
                    "sha": c["sha"],
                    "name": c["name"],
                    "email": c["email"],
                    "timestamp": c["timestamp"],
                    "subject": c["subject"],
                }
            )
            if len(out) >= GIT_LOG_CAP:
                break
        if path_f:
            # git log path filter via CLI for accuracy
            proc = git_cli.run_git_in(
                root,
                [
                    "log",
                    "HEAD",
                    f"--max-count={GIT_LOG_CAP}",
                    "--format=%H%x00%an%x00%ae%x00%at%x00%s",
                    "--",
                    path_f,
                ],
                check=False,
            )
            text = git_cli.decode(proc)
            parsed = []
            for line in text.splitlines():
                parts = line.split("\0")
                if len(parts) < 5:
                    continue
                parsed.append(
                    {
                        "sha": parts[0],
                        "name": parts[1],
                        "email": parts[2],
                        "timestamp": int(parts[3]) if parts[3].isdigit() else 0,
                        "subject": parts[4],
                    }
                )
            return parsed
        return out
    return {"error": f"unknown tool {name}"}


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
    return headers


def _accumulate_tool_calls(acc: dict[int, dict], deltas: list) -> None:
    for delta in deltas:
        idx = delta.get("index", 0)
        slot = acc.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
        if delta.get("id"):
            slot["id"] = delta["id"]
        fn = delta.get("function") or {}
        if fn.get("name"):
            slot["function"]["name"] += fn["name"]
        if fn.get("arguments"):
            slot["function"]["arguments"] += fn["arguments"]


def stream_chat(
    messages: list[dict],
    *,
    root: Path,
    checks: list[dict],
) -> Iterator[str]:
    """Yield SSE data payloads (JSON strings)."""
    if not llm_configured():
        yield json.dumps({"type": "error", "message": "LLM is not configured. Copy .env.example to .env and set OPENAI_API_KEY (or a local OPENAI_BASE_URL)."})
        return

    convo = list(messages)
    url = f"{OPENAI_BASE_URL}/chat/completions"

    with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
        for _round in range(TOOL_ROUND_CAP):
            acc_tools: dict[int, dict] = {}
            body = {
                "model": OPENAI_MODEL,
                "messages": convo,
                "tools": TOOLS,
                "stream": True,
            }
            try:
                with client.stream("POST", url, headers=_headers(), json=body) as resp:
                    if resp.status_code >= 400:
                        err = resp.read().decode("utf-8", "replace")
                        yield json.dumps({"type": "error", "message": f"LLM HTTP {resp.status_code}: {err[:800]}"})
                        return
                    for raw_line in resp.iter_lines():
                        if not raw_line:
                            continue
                        if raw_line.startswith(":"):
                            continue
                        if not raw_line.startswith("data:"):
                            continue
                        data = raw_line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choice = (payload.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            chunk = delta["content"]
                            yield json.dumps({"type": "token", "text": chunk})
                        if delta.get("tool_calls"):
                            _accumulate_tool_calls(acc_tools, delta["tool_calls"])
            except httpx.HTTPError as exc:
                yield json.dumps({"type": "error", "message": str(exc)})
                return

            if acc_tools:
                tool_calls = [acc_tools[i] for i in sorted(acc_tools)]
                convo.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                for call in tool_calls:
                    name = call["function"]["name"]
                    yield json.dumps({"type": "tool", "name": name})
                    try:
                        args = json.loads(call["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    try:
                        result = execute_tool(name, args, root=root, checks=checks)
                    except Exception as exc:
                        result = {"error": str(exc)}
                    convo.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or name,
                            "content": json.dumps(result, default=str)[: LLM_FILE_BYTES * 4],
                        }
                    )
                continue

            yield json.dumps({"type": "done"})
            return

        yield json.dumps({"type": "error", "message": "Too many tool rounds."})
