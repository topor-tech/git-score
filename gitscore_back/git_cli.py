from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from gitscore_back.config import GIT_EXECUTABLE

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


def _clean_git_error(stderr: str, fallback: str) -> str:
    text = stderr.replace("\x1b[K", "")
    for _phase, _unit, pattern in _PROGRESS_PATTERNS:
        text = pattern.sub("\n", text)
    text = re.sub(r"\d+%\s*\(\d+/\d+\)", "\n", text)
    text = re.sub(r"\(\d+/\d+\)", "\n", text)
    text = re.sub(r",\s*done\.?", "\n", text, flags=re.I)
    useful: list[str] = []
    for part in re.split(r"[\r\n]+", text):
        for piece in re.split(r"(?=warning:)", part, flags=re.I):
            cleaned = piece.strip(" \t,);:")
            if len(cleaned) < 8:
                continue
            if useful and useful[-1] == cleaned:
                continue
            useful.append(cleaned)
    return " ".join(useful[-3:]) if useful else fallback


def _usable_clone(dest: Path) -> bool:
    git_dir = dest / ".git"
    if not git_dir.exists():
        return False
    return bool(head_sha(dest))


def _retry_checkout(dest: Path) -> None:
    run_git_in(dest, ["config", "core.longpaths", "true"], check=False)
    run_git(
        ["-c", "core.longpaths=true", "-C", str(dest), "checkout", "-f", "HEAD"],
        timeout=180,
        check=False,
    )


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
        "-c",
        "core.longpaths=true",
        "clone",
        "--config",
        "core.longpaths=true",
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
        if _usable_clone(dest):
            _retry_checkout(dest)
            return
        raise GitError(_clean_git_error(err_tail, f"git clone failed ({code})"))


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


def count_objects(repo: Path) -> dict[str, str]:
    proc = run_git_in(repo, ["count-objects", "-vH"], check=False, timeout=30)
    out: dict[str, str] = {}
    if proc.returncode != 0:
        return out
    for line in decode(proc).splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        out[key.strip()] = val.strip()
    return out


def fsck(repo: Path, *, timeout: int = 90) -> dict:
    proc = run_git_in(repo, ["fsck", "--full", "--no-dangling"], check=False, timeout=timeout)
    stdout = decode(proc)
    stderr = proc.stderr.decode("utf-8", "replace")
    text = f"{stdout}\n{stderr}"
    errors: list[str] = []
    warnings: list[str] = []
    dangling: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "dangling" in low:
            dangling.append(line[:240])
        elif low.startswith("error") or "missing" in low or "corrupt" in low:
            errors.append(line[:240])
        elif low.startswith("warning"):
            warnings.append(line[:240])
    return {
        "returncode": proc.returncode,
        "errors": errors[:40],
        "warnings": warnings[:40],
        "dangling": dangling[:20],
        "truncated": len(errors) > 40 or len(warnings) > 40,
    }


def _strip_origin_prefix(ref: str) -> str | None:
    for prefix in ("refs/remotes/origin/", "origin/"):
        if ref.startswith(prefix):
            name = ref[len(prefix) :].strip()
            return name or None
    return None


def default_branch(repo: Path) -> tuple[str | None, str]:
    """Return (branch_name, source). Prefer origin/HEAD, then current HEAD."""
    proc = run_git_in(repo, ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], check=False)
    if proc.returncode == 0:
        ref = decode(proc).strip()
        name = _strip_origin_prefix(ref)
        if name:
            return name, "origin/HEAD"
        if ref:
            return ref.rsplit("/", 1)[-1], "origin/HEAD"
    proc = run_git_in(repo, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    if proc.returncode == 0:
        name = decode(proc).strip()
        if name and name != "HEAD":
            return name, "HEAD"
    return None, "none"


def branch_sha(repo: Path, name: str) -> str | None:
    for ref in (f"refs/heads/{name}", f"refs/remotes/origin/{name}"):
        proc = run_git_in(repo, ["rev-parse", "--verify", f"{ref}^{{commit}}"], check=False)
        if proc.returncode != 0:
            continue
        sha = decode(proc).strip()
        if sha:
            return sha
    return None


def branch_exists(repo: Path, name: str) -> bool:
    return bool(branch_sha(repo, name))


def ls_tree_sizes(repo: Path) -> list[dict]:
    proc = run_git_in(repo, ["ls-tree", "-r", "-l", "-z", "HEAD"], check=False, timeout=120)
    if proc.returncode != 0:
        return []
    rows: list[dict] = []
    for part in proc.stdout.split(b"\0"):
        if not part:
            continue
        # 100644 blob <sha> <size>\t<path>
        try:
            meta, path_b = part.split(b"\t", 1)
        except ValueError:
            continue
        fields = meta.decode("utf-8", "replace").split()
        if len(fields) < 4:
            continue
        try:
            size = int(fields[3])
        except ValueError:
            continue
        rows.append(
            {
                "mode": fields[0],
                "kind": fields[1],
                "sha": fields[2],
                "size": size,
                "path": path_b.decode("utf-8", "replace"),
            }
        )
    return rows


def remote_branches(repo: Path) -> list[dict]:
    proc = run_git_in(
        repo,
        ["for-each-ref", "--format=%(refname:short)%00%(committerdate:unix)%00%(objectname)", "refs/remotes"],
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        return []
    rows: list[dict] = []
    for line in decode(proc).splitlines():
        parts = line.split("\0")
        if len(parts) < 3:
            continue
        try:
            ts = int(parts[1])
        except ValueError:
            ts = 0
        rows.append({"name": parts[0], "timestamp": ts, "sha": parts[2]})
    return rows


def ref_count(repo: Path) -> int:
    proc = run_git_in(repo, ["for-each-ref", "--format=%(objectname)"], check=False, timeout=60)
    if proc.returncode != 0:
        return 0
    return sum(1 for line in decode(proc).splitlines() if line.strip())


def submodule_status(repo: Path) -> str:
    proc = run_git_in(repo, ["submodule", "status", "--recursive"], check=False, timeout=60)
    return decode(proc)


def log_name_only(repo: Path, max_count: int = 400) -> list[dict]:
    proc = run_git_in(
        repo,
        ["log", "HEAD", f"--max-count={max_count}", "--name-only", "--format=%H%x00%an%x00%ae%x00%at%x00%s"],
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        return []
    commits: list[dict] = []
    current: dict | None = None
    for line in decode(proc).splitlines():
        if not line.strip():
            continue
        if "\0" in line:
            parts = line.split("\0")
            if len(parts) < 5:
                continue
            current = {
                "sha": parts[0],
                "name": parts[1],
                "email": parts[2],
                "timestamp": int(parts[3]) if parts[3].isdigit() else 0,
                "subject": parts[4],
                "files": [],
            }
            commits.append(current)
            continue
        if current is not None:
            current["files"].append(line.strip())
    return commits


def signature_stats(repo: Path, limit: int = 200) -> dict:
    proc = run_git_in(
        repo,
        ["log", "HEAD", f"--max-count={limit}", "--pretty=%G?"],
        check=False,
        timeout=60,
    )
    counts = {"G": 0, "B": 0, "U": 0, "X": 0, "Y": 0, "R": 0, "E": 0, "N": 0, "other": 0}
    if proc.returncode != 0:
        return {"scanned": 0, "counts": counts}
    n = 0
    for line in decode(proc).splitlines():
        mark = (line.strip() or "?")[0]
        n += 1
        if mark in counts:
            counts[mark] += 1
        else:
            counts["other"] += 1
    return {"scanned": n, "counts": counts, "good": counts["G"]}


def is_shallow(repo: Path) -> bool:
    proc = run_git_in(repo, ["rev-parse", "--is-shallow-repository"], check=False)
    return decode(proc).strip().lower() == "true"


def merge_commit_count(repo: Path, limit: int = 400) -> tuple[int, int]:
    proc = run_git_in(
        repo,
        ["log", "HEAD", f"--max-count={limit}", "--pretty=%P"],
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        return 0, 0
    total = 0
    merges = 0
    for line in decode(proc).splitlines():
        parents = line.strip().split()
        if not parents:
            continue
        total += 1
        if len(parents) > 1:
            merges += 1
    return merges, total
