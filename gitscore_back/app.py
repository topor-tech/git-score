from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from gitscore_back import files as file_ops
from gitscore_back.config import DATA_DIR
from gitscore_back.files import PathEscapeError
from gitscore_back.jobs import enqueue, is_url
from gitscore_back.llm import llm_configured, stream_chat, system_prompt
from gitscore_back.store import Store
from gitscore_back.wiki import wiki_check, wiki_index

app = FastAPI(title="Git Score", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = Store()
DATA_DIR.mkdir(parents=True, exist_ok=True)


class CreateAnalysis(BaseModel):
    source: str = Field(min_length=1)


class ChatBody(BaseModel):
    message: str = Field(min_length=1)


def _parse_checks(row: dict) -> list[dict]:
    raw = row.get("checks_json")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _parse_progress(row: dict) -> dict | None:
    raw = row.get("progress")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _public_analysis(row: dict) -> dict:
    return {
        "id": row["id"],
        "source_type": row["source_type"],
        "source": row["source"],
        "working_copy": row.get("working_copy"),
        "head_sha": row.get("head_sha"),
        "status": row["status"],
        "error": row.get("error"),
        "checks": _parse_checks(row),
        "progress": _parse_progress(row),
        "created_at": row["created_at"],
        "completed_at": row.get("completed_at"),
        "chat_ready": row["status"] == "complete",
        "tree_ready": bool(row.get("working_copy"))
        and row["status"] in {"running_checks", "complete"},
    }


def _require(analysis_id: str) -> dict:
    row = store.get_analysis(analysis_id)
    if not row:
        raise HTTPException(404, "analysis not found")
    return row


def _root(row: dict) -> Path:
    wc = row.get("working_copy")
    if not wc:
        raise HTTPException(409, "working copy not ready")
    path = Path(wc)
    if not path.is_dir():
        raise HTTPException(409, "working copy missing on disk")
    return path


@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm_configured()}


@app.get("/api/catalog")
def get_catalog():
    return wiki_index()


@app.get("/api/catalog/{check_id}")
def get_catalog_check(check_id: str):
    page = wiki_check(check_id)
    if not page:
        raise HTTPException(404, "check not found")
    return page


@app.post("/api/analyses")
def create_analysis(body: CreateAnalysis):
    source = body.source.strip().strip('"')
    source_type = "url" if is_url(source) else "path"
    analysis_id = str(uuid.uuid4())
    store.create_analysis(analysis_id, source_type, source, status="queued")
    enqueue(store, analysis_id)
    row = store.get_analysis(analysis_id)
    return _public_analysis(row)


@app.get("/api/analyses")
def list_analyses():
    return [_public_analysis(r) for r in store.list_analyses()]


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str):
    return _public_analysis(_require(analysis_id))


@app.get("/api/analyses/{analysis_id}/tree")
def get_tree(analysis_id: str, path: str = ""):
    row = _require(analysis_id)
    try:
        return file_ops.list_dir(_root(row), path)
    except PathEscapeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/analyses/{analysis_id}/file")
def get_file(analysis_id: str, path: str):
    if not path:
        raise HTTPException(400, "path required")
    row = _require(analysis_id)
    try:
        return file_ops.read_file_for_ui(_root(row), path)
    except PathEscapeError as extra:
        raise HTTPException(400, str(extra)) from extra
    except FileNotFoundError as extra:
        raise HTTPException(404, str(extra)) from extra


@app.get("/api/analyses/{analysis_id}/messages")
def get_messages(analysis_id: str):
    _require(analysis_id)
    return store.list_messages(analysis_id)


@app.post("/api/analyses/{analysis_id}/chat")
def chat(analysis_id: str, body: ChatBody):
    row = _require(analysis_id)
    if row["status"] != "complete":
        raise HTTPException(409, "chat is available after checks finish")
    if row.get("error"):
        raise HTTPException(409, "analysis failed")
    user_text = body.message.strip()
    store.add_message(str(uuid.uuid4()), analysis_id, "user", user_text)

    checks = _parse_checks(row)
    history = store.list_messages(analysis_id)
    messages = [{"role": "system", "content": system_prompt(row, checks)}]
    for msg in history:
        if msg["role"] in {"user", "assistant"}:
            messages.append({"role": msg["role"], "content": msg["content"]})

    root = _root(row)
    parts: list[str] = []

    def generate():
        try:
            for payload in stream_chat(messages, root=root, checks=checks):
                yield f"data: {payload}\n\n"
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if parsed.get("type") == "token":
                    parts.append(parsed.get("text") or "")
                if parsed.get("type") == "error" and not parts:
                    store.add_message(str(uuid.uuid4()), analysis_id, "assistant", parsed.get("message") or "error")
        finally:
            text = "".join(parts).strip()
            if text:
                store.add_message(str(uuid.uuid4()), analysis_id, "assistant", text)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="spa")
