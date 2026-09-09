from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import git_cli
from .config import COMMIT_HISTORY_CAP, HIDDEN_DIR_NAMES
from .files import looks_like_credential

SOURCE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".scala",
    ".vue",
    ".svelte",
    ".m",
    ".mm",
}

CI_FILES = {
    ".gitlab-ci.yml",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
    "jenkinsfile",
    ".travis.yml",
}

TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec"}
OVERSIZE_BYTES = 1 * 1024 * 1024
HUGE_BYTES = 10 * 1024 * 1024
DAY = 86400


@dataclass
class RepoContext:
    path: Path
    head_sha: str | None
    tags: list[str] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    tracked: list[str] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)  # {path, size}


def _result(
    check_id: str,
    title: str,
    category: str,
    score: float | int,
    score_kind: str,
    summary: str,
    evidence: dict,
) -> dict:
    if score_kind == "binary":
        score = 1 if score else 0
    else:
        score = max(0.0, min(1.0, float(score)))
    return {
        "id": check_id,
        "title": title,
        "category": category,
        "score": score,
        "score_kind": score_kind,
        "summary": summary,
        "evidence": evidence,
    }


def _root_names(ctx: RepoContext) -> set[str]:
    names: set[str] = set()
    try:
        for child in ctx.path.iterdir():
            names.add(child.name)
    except OSError:
        pass
    return names


def _find_root_file(names: set[str], candidates: list[str]) -> str | None:
    lower = {n.lower(): n for n in names}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def _is_test_path(rel: str) -> bool:
    parts = Path(rel.replace("\\", "/")).parts
    if any(p in TEST_DIR_NAMES for p in parts):
        return True
    name = Path(rel).name.lower()
    stem = Path(rel).stem.lower()
    if stem.endswith("_test") or stem.startswith("test_"):
        return True
    if ".test." in name or name.endswith(".test.ts") or name.endswith(".test.js"):
        return True
    if ".spec." in name:
        return True
    return False


def _is_source_path(rel: str) -> bool:
    return Path(rel).suffix.lower() in SOURCE_EXTENSIONS


def build_context(path: Path) -> RepoContext:
    head = git_cli.head_sha(path)
    tags = git_cli.list_tags(path)
    commits = git_cli.commit_log(path, COMMIT_HISTORY_CAP)
    tracked = git_cli.ls_files(path)
    files: list[dict] = []
    root = path.resolve()

    def walk(directory: Path) -> None:
        try:
            children = list(directory.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_dir():
                if child.name in HIDDEN_DIR_NAMES:
                    continue
                try:
                    child.resolve().relative_to(root)
                except (ValueError, OSError):
                    continue
                walk(child)
            elif child.is_file():
                try:
                    rel = child.resolve().relative_to(root).as_posix()
                    size = child.stat().st_size
                except (ValueError, OSError):
                    continue
                files.append({"path": rel, "size": size})

    walk(root)
    return RepoContext(
        path=path,
        head_sha=head,
        tags=tags,
        commits=commits,
        tracked=tracked,
        files=files,
    )


def check_has_readme(ctx: RepoContext) -> dict:
    names = _root_names(ctx)
    found = _find_root_file(names, ["README", "README.md", "README.rst", "README.txt"])
    return _result(
        "has_readme",
        "Has README",
        "hygiene",
        1 if found else 0,
        "binary",
        f"Found {found} at repo root." if found else "No README at repo root.",
        {"paths": [found] if found else []},
    )


def check_has_license(ctx: RepoContext) -> dict:
    names = _root_names(ctx)
    found = _find_root_file(names, ["LICENSE", "LICENSE.md", "COPYING", "COPYING.md"])
    return _result(
        "has_license",
        "Has LICENSE",
        "hygiene",
        1 if found else 0,
        "binary",
        f"Found {found}." if found else "No LICENSE or COPYING at repo root.",
        {"paths": [found] if found else []},
    )


def check_has_gitignore(ctx: RepoContext) -> dict:
    names = _root_names(ctx)
    found = _find_root_file(names, [".gitignore"])
    return _result(
        "has_gitignore",
        "Has .gitignore",
        "hygiene",
        1 if found else 0,
        "binary",
        "Found .gitignore." if found else "No .gitignore at repo root.",
        {"paths": [".gitignore"] if found else []},
    )


def check_has_ci(ctx: RepoContext) -> dict:
    paths: list[str] = []
    names = {n.lower() for n in _root_names(ctx)}
    if "jenkinsfile" in names:
        # preserve actual casing
        for n in _root_names(ctx):
            if n.lower() == "jenkinsfile":
                paths.append(n)
    for n in _root_names(ctx):
        if n.lower() in CI_FILES:
            paths.append(n)
    workflows = ctx.path / ".github" / "workflows"
    if workflows.is_dir():
        for child in workflows.iterdir():
            if child.is_file() and child.suffix.lower() in {".yml", ".yaml"}:
                paths.append(f".github/workflows/{child.name}")
    circle = ctx.path / ".circleci" / "config.yml"
    if circle.is_file():
        paths.append(".circleci/config.yml")
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return _result(
        "has_ci",
        "Has CI config",
        "hygiene",
        1 if uniq else 0,
        "binary",
        f"Found CI config: {', '.join(uniq[:5])}." if uniq else "No common CI config found.",
        {"paths": uniq},
    )


def check_has_contributing(ctx: RepoContext) -> dict:
    names = _root_names(ctx)
    found = _find_root_file(names, ["CONTRIBUTING", "CONTRIBUTING.md"])
    return _result(
        "has_contributing",
        "Has CONTRIBUTING",
        "hygiene",
        1 if found else 0,
        "binary",
        f"Found {found}." if found else "No CONTRIBUTING file at repo root.",
        {"paths": [found] if found else []},
    )


def check_has_tags(ctx: RepoContext) -> dict:
    tags = ctx.tags
    return _result(
        "has_tags",
        "Has git tags",
        "hygiene",
        1 if tags else 0,
        "binary",
        f"{len(tags)} tag(s)." if tags else "No git tags.",
        {"counts": {"tags": len(tags)}, "samples": tags[:20]},
    )


def check_last_commit_recency(ctx: RepoContext) -> dict:
    if not ctx.commits:
        return _result(
            "last_commit_recency",
            "Last commit recency",
            "activity",
            0.0,
            "ratio",
            "No commits on HEAD.",
            {"counts": {"age_days": None}},
        )
    ts = ctx.commits[0]["timestamp"]
    age_days = max(0.0, (time.time() - ts) / DAY)
    if age_days <= 7:
        score = 1.0
    elif age_days >= 365:
        score = 0.0
    else:
        score = 1.0 - (age_days - 7) / (365 - 7)
    sha = ctx.commits[0]["sha"]
    return _result(
        "last_commit_recency",
        "Last commit recency",
        "activity",
        score,
        "ratio",
        f"HEAD is {age_days:.1f} days old ({sha[:12]}).",
        {
            "counts": {"age_days": round(age_days, 2)},
            "commits": [{"sha": sha, "subject": ctx.commits[0]["subject"]}],
        },
    )


def check_commit_volume_90d(ctx: RepoContext) -> dict:
    cutoff = time.time() - 90 * DAY
    n = sum(1 for c in ctx.commits if c["timestamp"] >= cutoff)
    score = min(1.0, n / 50.0)
    samples = [
        {"sha": c["sha"], "subject": c["subject"]}
        for c in ctx.commits
        if c["timestamp"] >= cutoff
    ][:8]
    return _result(
        "commit_volume_90d",
        "Commit volume (90d)",
        "activity",
        score,
        "ratio",
        f"{n} commit(s) in the last 90 days (cap 50 → 1.0).",
        {"counts": {"commits_90d": n, "history_scanned": len(ctx.commits)}, "commits": samples},
    )


def check_bus_factor(ctx: RepoContext) -> dict:
    if not ctx.commits:
        return _result(
            "bus_factor",
            "Bus factor",
            "community",
            0.0,
            "ratio",
            "No commits; treating bus factor as 0.",
            {"counts": {"total_commits": 0}},
        )
    counts: dict[str, int] = {}
    for c in ctx.commits:
        key = c["email"] or c["name"] or "unknown"
        counts[key] = counts.get(key, 0) + 1
    total = len(ctx.commits)
    top_author, top_n = max(counts.items(), key=lambda kv: kv[1])
    score = 1.0 - (top_n / total)
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    authors = [{"name": a, "commits": n} for a, n in ranked[:15]]
    return _result(
        "bus_factor",
        "Bus factor",
        "community",
        score,
        "ratio",
        f"Top author {top_author} has {top_n}/{total} commits.",
        {"counts": {"total_commits": total, "top_author_commits": top_n}, "authors": authors},
    )


def check_active_authors_90d(ctx: RepoContext) -> dict:
    cutoff = time.time() - 90 * DAY
    authors: set[str] = set()
    for c in ctx.commits:
        if c["timestamp"] >= cutoff:
            authors.add(c["email"] or c["name"] or "unknown")
    n = len(authors)
    score = min(1.0, n / 5.0)
    return _result(
        "active_authors_90d",
        "Active authors (90d)",
        "community",
        score,
        "ratio",
        f"{n} distinct author(s) in the last 90 days (cap 5 → 1.0).",
        {"counts": {"active_authors_90d": n}, "authors": sorted(authors)[:20]},
    )


def check_has_tests(ctx: RepoContext) -> dict:
    test_paths = [f["path"] for f in ctx.files if _is_test_path(f["path"])]
    return _result(
        "has_tests",
        "Has tests",
        "structure",
        1 if test_paths else 0,
        "binary",
        f"Found {len(test_paths)} test file(s)." if test_paths else "No conventional test files found.",
        {"counts": {"test_files": len(test_paths)}, "paths": test_paths[:30]},
    )


def check_test_file_ratio(ctx: RepoContext) -> dict:
    tests = [f["path"] for f in ctx.files if _is_test_path(f["path"])]
    sources = [f["path"] for f in ctx.files if _is_source_path(f["path"]) and not _is_test_path(f["path"])]
    denom = len(tests) + len(sources)
    score = 0.0 if denom == 0 else len(tests) / denom
    return _result(
        "test_file_ratio",
        "Test file ratio",
        "structure",
        score,
        "ratio",
        f"{len(tests)} test / {len(tests) + len(sources)} source+test files.",
        {"counts": {"test_files": len(tests), "source_files": len(sources)}},
    )


def check_no_oversized_files(ctx: RepoContext) -> dict:
    oversized = [f for f in ctx.files if f["size"] > OVERSIZE_BYTES]
    score = max(0.0, 1.0 - 0.2 * len(oversized))
    paths = [f["path"] for f in sorted(oversized, key=lambda x: -x["size"])[:20]]
    return _result(
        "no_oversized_files",
        "No oversized files",
        "structure",
        score,
        "ratio",
        f"{len(oversized)} file(s) larger than 1 MiB." if oversized else "No working-tree files over 1 MiB.",
        {
            "counts": {"oversized": len(oversized)},
            "paths": paths,
            "sizes": {f["path"]: f["size"] for f in oversized[:20]},
        },
    )


def check_no_huge_blobs(ctx: RepoContext) -> dict:
    huge = [f for f in ctx.files if f["size"] >= HUGE_BYTES]
    if not huge:
        score = 1.0
        summary = "No files ≥ 10 MiB."
    else:
        score = max(0.0, 1.0 - 0.25 * len(huge))
        summary = f"{len(huge)} file(s) ≥ 10 MiB."
    return _result(
        "no_huge_blobs",
        "No huge blobs",
        "risk",
        score,
        "ratio",
        summary,
        {
            "counts": {"huge": len(huge)},
            "paths": [f["path"] for f in huge[:20]],
        },
    )


def check_commit_message_quality(ctx: RepoContext) -> dict:
    if not ctx.commits:
        return _result(
            "commit_message_quality",
            "Commit message quality",
            "risk",
            0.0,
            "ratio",
            "No commits to score.",
            {"counts": {"scanned": 0, "good": 0}},
        )
    good = 0
    weak_samples = []
    for c in ctx.commits:
        subject = (c["subject"] or "").strip()
        if len(subject) >= 10:
            good += 1
        elif len(weak_samples) < 8:
            weak_samples.append({"sha": c["sha"], "subject": subject})
    score = good / len(ctx.commits)
    return _result(
        "commit_message_quality",
        "Commit message quality",
        "risk",
        score,
        "ratio",
        f"{good}/{len(ctx.commits)} commit subjects are non-empty and ≥ 10 characters.",
        {
            "counts": {"scanned": len(ctx.commits), "good": good},
            "commits": weak_samples,
        },
    )


def check_no_credential_filenames(ctx: RepoContext) -> dict:
    flagged = [f["path"] for f in ctx.files if looks_like_credential(f["path"])]
    # also tracked paths that might be skipped by walk? walk covers working tree
    for p in ctx.tracked:
        if looks_like_credential(p) and p not in flagged:
            flagged.append(p)
    return _result(
        "no_credential_filenames",
        "No credential filenames",
        "risk",
        0 if flagged else 1,
        "binary",
        f"Flagged {len(flagged)} credential-like path(s)." if flagged else "No obvious credential filenames.",
        {"paths": flagged[:50], "counts": {"flagged": len(flagged)}},
    )


CATALOG = [
    check_has_readme,
    check_has_license,
    check_has_gitignore,
    check_has_ci,
    check_has_contributing,
    check_has_tags,
    check_last_commit_recency,
    check_commit_volume_90d,
    check_bus_factor,
    check_active_authors_90d,
    check_has_tests,
    check_test_file_ratio,
    check_no_oversized_files,
    check_no_huge_blobs,
    check_commit_message_quality,
    check_no_credential_filenames,
]


def run_all(ctx: RepoContext, on_each=None) -> list[dict]:
    results: list[dict] = []
    for fn in CATALOG:
        item = fn(ctx)
        results.append(item)
        if on_each:
            on_each(results)
    return results
