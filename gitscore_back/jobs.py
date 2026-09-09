from __future__ import annotations

import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from gitscore_back import git_cli
from gitscore_back.catalog import BY_ID, CHECKS
from gitscore_back.checks import build_context, run_all
from gitscore_back.config import CLONES_DIR
from gitscore_back.git_cli import GitError
from gitscore_back.store import Store

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
        total_checks = len(CHECKS)
        store.update_analysis(
            analysis_id,
            working_copy=str(working),
            head_sha=git_cli.head_sha(working),
            status="running_checks",
            checks_json=json.dumps([]),
            progress=json.dumps(
                {
                    "phase": "indexing",
                    "percent": 0,
                    "current": 0,
                    "total": total_checks,
                    "label": f"0/{total_checks} reading history",
                }
            ),
        )
        ctx = build_context(working)

        def persist(results: list[dict], check_id: str = "", i: int = 0, total: int = 0) -> None:
            title = BY_ID.get(check_id, {}).get("title", "")
            if check_id and title:
                label = f"{i}/{total} {check_id} {title}"
            elif check_id:
                label = f"{i}/{total} {check_id}"
            else:
                label = f"{i}/{total}"
            store.update_analysis(
                analysis_id,
                checks_json=json.dumps(results),
                progress=json.dumps(
                    {
                        "phase": "checks",
                        "percent": int(100 * i / total) if total else 0,
                        "current": i,
                        "total": total,
                        "check_id": check_id or None,
                        "label": label,
                    }
                ),
            )

        persist([], "", 0, total_checks)
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
        store.update_analysis(
            analysis_id,
            status="cloning",
            progress=json.dumps({"phase": "starting", "percent": 0, "label": "starting clone"}),
        )
        if not dest.exists():

            def _progress(info: dict) -> None:
                store.update_analysis(analysis_id, progress=json.dumps(info))

            git_cli.clone(source, dest, on_progress=_progress)
        return dest
    path = Path(source).expanduser().resolve()
    if not path.is_dir():
        raise GitError(f"Not a directory: {path}")
    if not git_cli.is_git_work_tree(path):
        raise GitError(f"Not a git work tree: {path}")
    return path
