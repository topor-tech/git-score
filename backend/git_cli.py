from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .config import GIT_EXECUTABLE

ProgressFn = Callable[[dict], None]

_PROGRESS_PATTERNS = (
    (
        "receiving",
        "objects",
        re.compile(
            r"Receiving objects:\s+(\d+)%\s+\((\d+)/(\d+)\)(?:,\s*([^,\r\n]+))?",
            re.I,
        ),
    ),
    (
        "checkout",
        "files",
        re.compile(r"Checking out files:\s+(\d+)%\s+\((\d+)/(\d+)\)", re.I),
    ),
    (
        "deltas",
        "deltas",
        re.compile(r"Resolving deltas:\s+(\d+)%\s+\((\d+)/(\d+)\)", re.I),
    ),
    (
        "compressing",
        "objects",
        re.compile(r"(?:remote:\s+)?Compressing objects:\s+(\d+)%\s+\((\d+)/(\d+)\)", re.I),
    ),
    (
        "counting",
        "objects",
        re.compile(r"(?:remote:\s+)?Counting objects:\s+(\d+)%\s+\((\d+)/(\d+)\)", re.I),
    ),
)


class GitError(Exception):
    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    cmd = [GIT_EXECUTABLE, "--no-pager", "-c", "core.quotepath=false", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=_env(),
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GitError(
            f"Git executable not found ({GIT_EXECUTABLE}). Install Git and put it on PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {' '.join(args)} timed out after {timeout}s") from exc
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(err or f"git {' '.join(args)} failed ({proc.returncode})", err)
    return proc


def run_git_in(
    repo: Path,
    args: list[str],
    *,
    timeout: int = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    return run_git(["-C", str(repo), *args], timeout=timeout, check=check)


def decode(proc: subprocess.CompletedProcess[bytes]) -> str:
    return proc.stdout.decode("utf-8", "replace")


def parse_clone_progress(line: str) -> dict | None:
    text = line.strip().strip("\x1b[K")
    if not text:
        return None
    for phase, unit, pattern in _PROGRESS_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        percent = int(match.group(1))
        current = int(match.group(2))
        total = int(match.group(3))
        extra = ""
        if match.lastindex and match.lastindex >= 4 and match.group(4):
            extra = match.group(4).strip()
            if extra.lower().rstrip(".") == "done":
                extra = ""
        size = extra.split("|", 1)[0].strip() if extra else ""
        label = f"{current}/{total} {unit}"
        if size:
            label = f"{label} · {size}"
        return {
            "phase": phase,
            "percent": percent,
            "current": current,
            "total": total,
            "unit": unit,
            "size": size or None,
            "label": label,
        }
    return None


def clone(
    url: str,
    dest: Path,
    *,
    timeout: int = 300,
    on_progress: ProgressFn | None = None,
) -> None:
    """Full clone so 90-day activity/community checks see real history."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        GIT_EXECUTABLE,
        "--no-pager",
        "-c",
        "core.quotepath=false",
        "clone",
        "--progress",
        "--",
        url,
        str(dest),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=_env(),
            bufsize=0,
        )
    except FileNotFoundError as extra:
        raise GitError(
            f"Git executable not found ({GIT_EXECUTABLE}). Install Git and put it on PATH."
        ) from extra
    if proc.stderr is None:
        raise GitError("git clone stderr pipe missing")

    chunks: queue.Queue[bytes | None] = queue.Queue()

    def _reader() -> None:
        assert proc.stderr is not None
        try:
            while True:
                piece = proc.stderr.read(512)
                if not piece:
                    break
                chunks.put(piece)
        finally:
            chunks.put(None)

    threading.Thread(target=_reader, daemon=True).start()
    buf = ""
    err_tail = ""
    deadline = time.monotonic() + timeout
    last_emit = 0.0
    last_key: tuple | None = None

    def _emit(part: str) -> None:
        nonlocal last_emit, last_key
        parsed = parse_clone_progress(part)
        if not parsed or on_progress is None:
            return
        key = (parsed["phase"], parsed["percent"], parsed["current"], parsed.get("size"))
        now = time.monotonic()
        if key == last_key and now - last_emit < 0.25:
            return
        last_key = key
        last_emit = now
        on_progress(parsed)

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                proc.kill()
                raise GitError(f"git clone timed out after {timeout}s")
            try:
                piece = chunks.get(timeout=min(0.4, remaining))
            except queue.Empty:
                continue
            if piece is None:
                break
            text = piece.decode("utf-8", "replace")
            err_tail = (err_tail + text)[-2000:]
            buf += text
            parts = re.split(r"[\r\n]+", buf)
            buf = parts.pop() if parts else ""
            for part in parts:
                _emit(part)
        _emit(buf)
        code = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise GitError("git clone timed out") from None
    if code != 0:
        detail = err_tail.strip() or f"git clone failed ({code})"
        raise GitError(detail)


def is_git_work_tree(path: Path) -> bool:
    proc = run_git_in(path, ["rev-parse", "--is-inside-work-tree"], check=False)
    if proc.returncode != 0:
        return False
    return decode(proc).strip().lower() == "true"


def head_sha(repo: Path) -> str | None:
    proc = run_git_in(repo, ["rev-parse", "HEAD"], check=False)
    if proc.returncode != 0:
        return None
    sha = decode(proc).strip()
    return sha or None


def list_tags(repo: Path) -> list[str]:
    proc = run_git_in(repo, ["tag"], check=False)
    if proc.returncode != 0:
        return []
    text = decode(proc).strip()
    return [line for line in text.splitlines() if line]


def ls_files(repo: Path) -> list[str]:
    proc = run_git_in(repo, ["ls-files", "-z"], check=False)
    if proc.returncode != 0:
        return []
    raw = proc.stdout.split(b"\0")
    out: list[str] = []
    for part in raw:
        if not part:
            continue
        out.append(part.decode("utf-8", "replace"))
    return out


def commit_log(repo: Path, limit: int) -> list[dict]:
    """HEAD ancestry only. Fields: sha, name, email, timestamp, subject."""
    proc = run_git_in(
        repo,
        [
            "log",
            "HEAD",
            f"--max-count={limit}",
            "--format=%H%x00%an%x00%ae%x00%at%x00%s",
        ],
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        return []
    text = decode(proc)
    commits: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\0")
        if len(parts) < 5:
            continue
        sha, name, email, ts, subject = parts[0], parts[1], parts[2], parts[3], parts[4]
        try:
            timestamp = int(ts)
        except ValueError:
            timestamp = 0
        commits.append(
            {
                "sha": sha,
                "name": name,
                "email": email,
                "timestamp": timestamp,
                "subject": subject,
            }
        )
    return commits
