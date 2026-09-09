from __future__ import annotations

import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import git_cli
from .checks import build_context, run_all
from .config import CLONES_DIR
from .git_cli import GitError
from .store import Store

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")


def is_url(source: str) -> bool:
    s = source.strip()
    return s.startswith(("http://", "https://", "git@", "ssh://", "git://"))


def enqueue(store: Store, analysis_id: str) -> None:
    _executor.submit(_run, store, analysis_id)


def _run(store: Store, analysis_id: str) -> None:
    row = store.get_analysis(analysis_id)
    if not row:
        return
    try:
        working = _prepare_working_copy(store, row)
        store.update_analysis(
            analysis_id,
            working_copy=str(working),
            head_sha=git_cli.head_sha(working),
            status="running_checks",
            checks_json=json.dumps([]),
        )
        ctx = build_context(working)

        def persist(results: list[dict]) -> None:
            store.update_analysis(analysis_id, checks_json=json.dumps(results))

        run_all(ctx, on_each=persist)
        store.update_analysis(
            analysis_id,
            status="complete",
            head_sha=ctx.head_sha,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except GitError as exc:
        store.update_analysis(analysis_id, status="failed", error=str(exc))
    except Exception as exc:
        store.update_analysis(
            analysis_id,
            status="failed",
            error=f"{exc}\n{traceback.format_exc()}",
        )


def _prepare_working_copy(store: Store, row: dict) -> Path:
    source = row["source"]
    analysis_id = row["id"]
    if row["source_type"] == "url":
        dest = CLONES_DIR / analysis_id
        store.update_analysis(analysis_id, status="cloning")
        if not dest.exists():
            git_cli.clone(source, dest)
        return dest
    path = Path(source).expanduser().resolve()
    if not path.is_dir():
        raise GitError(f"Not a directory: {path}")
    if not git_cli.is_git_work_tree(path):
        raise GitError(f"Not a git work tree: {path}")
    return path
