from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import GIT_EXECUTABLE


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


def clone(url: str, dest: Path, *, timeout: int = 300) -> None:
    """Full clone so 90-day activity/community checks see real history."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_git(["clone", "--", url, str(dest)], timeout=timeout)


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
