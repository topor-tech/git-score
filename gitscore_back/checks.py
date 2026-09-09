from __future__ import annotations

import fnmatch
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from gitscore_back import git_cli
from gitscore_back.catalog import BY_ID, CHECKS, GROUPS
from gitscore_back.config import COMMIT_HISTORY_CAP, HIDDEN_DIR_NAMES
from gitscore_back.files import looks_like_credential

DAY = 86400
LARGE_BLOB = 10 * 1024 * 1024
HUGE_BLOB = 50 * 1024 * 1024
LOOSE_WARN = 1000
REF_WARN = 5000
STALE_BRANCH_DAYS = 90
MAINTAINED_DAYS = 90
ABSENCE_WINDOW_DAYS = 180
CHURN_WINDOW_DAYS = 30
HOTSPOT_WINDOW_DAYS = 180
BATCH_WINDOW_DAYS = 90

SECRET_CONTENT_RE = re.compile(
    r"(AKIA[0-9A-Z]{16}|-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----|"
    r"ghp_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_\-]{20,}|xox[baprs]-)",
    re.IGNORECASE,
)
ISSUE_REF_RE = re.compile(
    r"(#\d+|closes\s+#\d+|fixes\s+#\d+|[A-Z][A-Z0-9]+-\d+|https?://\S+)",
    re.I,
)
CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\(.+\))?!?: ",
    re.I,
)
PINNED_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}", re.I)

SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java",
    ".kt", ".kts", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php",
    ".swift", ".scala", ".vue", ".svelte", ".m", ".mm",
}
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".7z", ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf",
    ".mp3", ".mp4", ".class", ".pyc", ".o", ".wasm", ".bin",
}
GENERATED_DIR_PARTS = {
    "node_modules", "vendor", "dist", "build", "target", "__pycache__",
    ".venv", "venv", "coverage", "generated", "gen",
}
ARTIFACT_NAME_RE = re.compile(
    r"(^|/)("
    r"\.env$|\.env\.[^/]+$|id_rsa$|id_dsa$|credentials\.json$|.*\.pem$|"
    r".*\.log$|.*\.dump$|.*\.sql\.gz$|\.ds_store$|thumbs\.db$|"
    r".*\.pyc$|.*\.class$|.*\.o$|"
    r"dump\.rdb$|core\.\d+$"
    r")",
    re.I,
)
ARTIFACT_DIR_RE = re.compile(
    r"(^|/)(node_modules|__pycache__|\.pytest_cache|\.mypy_cache|dist|build|\.tox|\.next)(/|$)",
    re.I,
)
CI_ROOT_FILES = {
    ".gitlab-ci.yml", "azure-pipelines.yml", "azure-pipelines.yaml",
    "jenkinsfile", ".travis.yml",
}
README_HINTS = ("readme",)
RUN_HINTS = ("install", "getting started", "quick start", "usage", "run ", "how to")
TEST_HINTS = ("test", "pytest", "npm test", "ci")
OWNER_HINTS = ("owner", "maintain", "contact", "support", "team")
DEPLOY_HINTS = ("deploy", "runbook", "operations", "production")

LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb",
    "uv.lock", "poetry.lock", "pipfile.lock", "cargo.lock", "composer.lock",
    "gemfile.lock", "go.sum", "pnpm-lock.yml",
}
MANIFESTS = {
    "package.json", "pyproject.toml", "pipfile", "requirements.txt", "cargo.toml",
    "go.mod", "composer.json", "gemfile", "pom.xml", "build.gradle",
    "build.gradle.kts",
}
UPDATE_CONFIGS = (
    "renovate.json", "renovate.json5", ".renovaterc", ".renovaterc.json",
    ".github/dependabot.yml", ".github/dependabot.yaml",
)
SBOM_NAMES = ("sbom.json", "bom.json", "cyclonedx.json", "spdx.json")
CODEOWNERS_CANDIDATES = (
    "CODEOWNERS", ".gitlab/CODEOWNERS", "docs/CODEOWNERS", ".github/CODEOWNERS",
)


@dataclass
class RepoContext:
    path: Path
    head_sha: str | None
    tags: list[str] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    tracked: list[str] = field(default_factory=list)
    tree: list[dict] = field(default_factory=list)
    counts: dict[str, str] = field(default_factory=dict)
    shallow: bool = False
    default_branch: str | None = None
    default_branch_source: str = "none"
    remote_branches: list[dict] = field(default_factory=list)
    name_log: list[dict] = field(default_factory=list)
    now: float = field(default_factory=time.time)

    def tracked_set(self) -> set[str]:
        return set(self.tracked)

    def posix_exists(self, rel: str) -> bool:
        return (self.path / rel).is_file()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result(
    check_id: str,
    *,
    status: str | None,
    summary: str,
    evidence: dict | None = None,
    observations: dict | None = None,
    reason_code: str | None = None,
    remediation: str | None = None,
    evidence_flags: dict | None = None,
    data_quality: dict | None = None,
    score: float | None = None,
) -> dict:
    meta = BY_ID[check_id]
    gid = check_id[0]
    mode = meta["evaluation_mode"]
    if mode == "observation":
        out_status = None if status not in {"UNKNOWN", "NOT_APPLICABLE"} else status
        out_score = None if out_status in {None, "UNKNOWN", "NOT_APPLICABLE"} else score
    else:
        out_status = status
        if score is None and status == "PASS":
            out_score = 1.0
        elif score is None and status == "WARN":
            out_score = 0.5
        elif score is None and status == "FAIL":
            out_score = 0.0
        else:
            out_score = score
    return {
        "id": check_id,
        "check_id": check_id,
        "title": meta["title"],
        "category": gid,
        "group": gid,
        "group_title": GROUPS[gid]["title"],
        "tags": meta["tags"],
        "importance": meta["importance"],
        "evaluation_mode": mode,
        "check_type": meta["check_type"],
        "definition_version": "0.1",
        "policy_version": "internal-production-0.1",
        "evaluated_at": _now_iso(),
        "status": out_status,
        "score": out_score,
        "summary": summary,
        "evidence": evidence or {},
        "observations": observations or {},
        "evidence_flags": evidence_flags or {},
        "data_quality": data_quality or {"complete": reason_code is None, "missing_sources": []},
        "reason_code": reason_code,
        "remediation": remediation,
        "blocker": False,
        "exception": None,
        "wiki_id": check_id,
    }


def _unknown(check_id: str, reason: str, summary: str, *, missing: list[str] | None = None, remediation: str | None = None) -> dict:
    return _result(
        check_id,
        status="UNKNOWN",
        summary=summary,
        reason_code=reason,
        remediation=remediation,
        data_quality={"complete": False, "missing_sources": missing or []},
    )


def _gitlab_unknown(check_id: str, what: str) -> dict:
    return _unknown(
        check_id,
        "UNSUPPORTED_ADAPTER",
        f"Cannot evaluate {what} from a local clone. GitLab project API is required.",
        missing=["gitlab_api"],
        remediation="Connect a GitLab token with read access to project merge/approval settings, then re-run.",
    )


def _root_names(ctx: RepoContext) -> dict[str, str]:
    names: dict[str, str] = {}
    try:
        for child in ctx.path.iterdir():
            names[child.name.lower()] = child.name
    except OSError:
        pass
    return names


def _find_root(ctx: RepoContext, candidates: list[str]) -> str | None:
    names = _root_names(ctx)
    for cand in candidates:
        if cand.lower() in names:
            return names[cand.lower()]
    return None


def _find_any(ctx: RepoContext, rels: tuple[str, ...]) -> list[str]:
    found = []
    tracked = ctx.tracked_set()
    lower = {p.lower(): p for p in tracked}
    for rel in rels:
        if rel.lower() in lower:
            found.append(lower[rel.lower()])
            continue
        if (ctx.path / rel).is_file():
            found.append(rel.replace("\\", "/"))
    return found


def _read_text(ctx: RepoContext, rel: str, limit: int = 80_000) -> str:
    path = ctx.path / rel
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return ""
    return data.decode("utf-8", "replace")


def _glob_tracked(ctx: RepoContext, pattern: str) -> list[str]:
    pat = pattern.replace("\\", "/").lstrip("/")
    return [p for p in ctx.tracked if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(Path(p).name, pat)]


def _is_test_path(rel: str) -> bool:
    parts = Path(rel.replace("\\", "/")).parts
    if any(p in {"test", "tests", "__tests__", "spec"} for p in parts):
        return True
    name = Path(rel).name.lower()
    stem = Path(rel).stem.lower()
    if stem.endswith("_test") or stem.startswith("test_"):
        return True
    if ".test." in name or ".spec." in name:
        return True
    return False


def _is_generated(rel: str) -> bool:
    parts = Path(rel.replace("\\", "/")).parts
    if any(p in GENERATED_DIR_PARTS or p in HIDDEN_DIR_NAMES for p in parts):
        return True
    low = rel.lower()
    if low.endswith(".min.js") or low.endswith(".min.css"):
        return True
    return False


def _is_binary_path(rel: str, size: int | None = None) -> bool:
    if Path(rel).suffix.lower() in BINARY_EXTENSIONS:
        return True
    if size is not None and size > 0 and Path(rel).suffix.lower() not in SOURCE_EXTENSIONS:
        # heuristic: no newline-ish small text files handled elsewhere
        if Path(rel).suffix.lower() in {".svg", ".json", ".md", ".yml", ".yaml", ".toml", ".txt", ".xml", ".html", ".css"}:
            return False
    return Path(rel).suffix.lower() in BINARY_EXTENSIONS


def _ci_paths(ctx: RepoContext) -> list[str]:
    found: list[str] = []
    names = _root_names(ctx)
    for key, actual in names.items():
        if key in CI_ROOT_FILES or key == "jenkinsfile":
            found.append(actual)
    for p in ctx.tracked:
        low = p.lower()
        if low.startswith(".github/workflows/") and low.endswith((".yml", ".yaml")):
            found.append(p)
        elif low == ".circleci/config.yml":
            found.append(p)
        elif low.startswith(".gitlab/") and "ci" in Path(p).name.lower() and low.endswith((".yml", ".yaml")):
            found.append(p)
    # unique
    seen: set[str] = set()
    out = []
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _codeowners_path(ctx: RepoContext) -> str | None:
    hits = _find_any(ctx, CODEOWNERS_CANDIDATES)
    return hits[0] if hits else None


def _parse_codeowners(text: str) -> list[tuple[str, list[str], bool]]:
    """Return (pattern, owners, optional_section)."""
    rules: list[tuple[str, list[str], bool]] = []
    optional = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            inner = line[1:-1]
            optional = inner.startswith("^")
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern, owners = parts[0], parts[1:]
        rules.append((pattern, owners, optional))
    return rules


def _codeowners_match(pattern: str, path: str) -> bool:
    pat = pattern.replace("\\", "/")
    if pat.startswith("/"):
        pat = pat[1:]
    path = path.replace("\\", "/")
    if pat.endswith("/"):
        return path.startswith(pat) or fnmatch.fnmatch(path, pat + "*")
    if "**" in pat:
        rx = re.escape(pat).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        return re.fullmatch(rx, path) is not None
    return fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, pat.rstrip("/") + "/*")


def _has_keywords(text: str, groups: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(k in low for k in groups)


def _identity(commit: dict) -> str:
    return (commit.get("email") or commit.get("name") or "unknown").lower()


def _absence_factor(weights: dict[str, float]) -> int | None:
    total = sum(weights.values())
    if total <= 0:
        return None
    ranked = sorted(weights.values(), reverse=True)
    acc = 0.0
    for i, w in enumerate(ranked, start=1):
        acc += w
        if acc / total >= 0.5:
            return i
    return len(ranked)


def _bytes_from_count(raw: str | None) -> int | None:
    if not raw:
        return None
    # "12.3 MiB" or "1234"
    m = re.match(r"([\d.]+)\s*([KMGT]i?B)?", raw.replace(",", ""), re.I)
    if not m:
        return None
    n = float(m.group(1))
    unit = (m.group(2) or "").lower()
    mul = {"": 1, "kb": 1000, "kib": 1024, "mb": 1_000_000, "mib": 1024**2, "gb": 1_000_000_000, "gib": 1024**3}
    return int(n * mul.get(unit, 1))


def build_context(path: Path) -> RepoContext:
    head = git_cli.head_sha(path)
    branch, src = git_cli.default_branch(path)
    return RepoContext(
        path=path,
        head_sha=head,
        tags=git_cli.list_tags(path),
        commits=git_cli.commit_log(path, COMMIT_HISTORY_CAP),
        tracked=git_cli.ls_files(path),
        tree=git_cli.ls_tree_sizes(path),
        counts=git_cli.count_objects(path),
        shallow=git_cli.is_shallow(path),
        default_branch=branch,
        default_branch_source=src,
        remote_branches=git_cli.remote_branches(path),
        name_log=git_cli.log_name_only(path, 500),
    )


# --- R ---

def check_r01(ctx: RepoContext) -> dict:
    data = git_cli.fsck(ctx.path)
    flags = {"declared": True, "configured": True, "enforced": None, "observed": True}
    quality = {"complete": not ctx.shallow, "missing_sources": ["full_history"] if ctx.shallow else []}
    if data["errors"]:
        return _result(
            "R01",
            status="FAIL",
            summary=f"git fsck reported {len(data['errors'])} integrity error(s).",
            evidence={"errors": data["errors"], "warnings": data["warnings"][:8]},
            evidence_flags=flags,
            data_quality=quality,
            remediation="Restore missing or corrupted objects from a trusted remote and re-run git fsck.",
        )
    if data["warnings"]:
        return _result(
            "R01",
            status="WARN",
            summary=f"Objects look connected; {len(data['warnings'])} fsck warning(s) need review.",
            evidence={"warnings": data["warnings"], "dangling_omitted": True},
            evidence_flags=flags,
            data_quality=quality,
            remediation="Inspect fsck warnings; historic format issues differ from data loss.",
        )
    extra = " Shallow clone: this does not prove server-side history." if ctx.shallow else ""
    return _result(
        "R01",
        status="PASS",
        summary=f"Available Git objects passed fsck --full (dangling omitted).{extra}",
        evidence={"returncode": data["returncode"], "shallow": ctx.shallow},
        evidence_flags=flags,
        data_quality=quality,
    )


def check_r02(ctx: RepoContext) -> dict:
    name = ctx.default_branch
    source = ctx.default_branch_source
    if not name:
        return _result(
            "R02",
            status="FAIL",
            summary="No default branch could be resolved from origin/HEAD or HEAD.",
            evidence={"source": source},
            evidence_flags={"declared": False, "configured": False, "enforced": None, "observed": True},
            remediation="Set origin/HEAD / server default branch to an existing branch with at least one commit.",
        )
    exists = git_cli.branch_exists(ctx.path, name)
    if not exists or not ctx.head_sha:
        return _result(
            "R02",
            status="FAIL",
            summary=f"Default branch '{name}' does not resolve to a commit.",
            evidence={"branch": name, "source": source, "head": ctx.head_sha},
            evidence_flags={"declared": True, "configured": False, "observed": True},
            remediation="Create the advertised default branch or fix origin/HEAD.",
        )
    note = ""
    if source != "origin/HEAD":
        note = " Server default was not advertised; used local HEAD."
        status = "WARN"
    else:
        status = "PASS"
    return _result(
        "R02",
        status=status,
        summary=f"Default branch '{name}' exists and resolves to a commit.{note}",
        evidence={"branch": name, "source": source, "head": ctx.head_sha},
        evidence_flags={"declared": source == "origin/HEAD", "configured": True, "observed": True},
        remediation="Point origin/HEAD at the server default branch." if status == "WARN" else None,
    )


def check_r03(ctx: RepoContext) -> dict:
    size_in_pack = ctx.counts.get("size-pack") or ctx.counts.get("size")
    in_pack = ctx.counts.get("in-pack")
    packs = ctx.counts.get("packs")
    return _result(
        "R03",
        status=None,
        summary=f"Object database size-pack={size_in_pack or 'unknown'}; packs={packs or 'n/a'}. No size policy applied.",
        evidence={"count_objects": ctx.counts},
        observations={"size_pack": size_in_pack, "in_pack": in_pack, "packs": packs},
        evidence_flags={"observed": True},
    )


def check_r04(ctx: RepoContext) -> dict:
    current = [t for t in ctx.tree if t["kind"] == "blob" and t["size"] >= LARGE_BLOB]
    huge = [t for t in current if t["size"] >= HUGE_BLOB]
    paths = [t["path"] for t in sorted(current, key=lambda x: -x["size"])[:25]]
    sizes = {t["path"]: t["size"] for t in current[:25]}
    if huge:
        status = "FAIL"
        summary = f"{len(huge)} tracked blob(s) ≥ 50 MiB in HEAD; {len(current)} ≥ 10 MiB."
        rem = "Move large assets to LFS or artifact storage; do not keep them in Git history of the default tree."
    elif current:
        status = "WARN"
        summary = f"{len(current)} tracked blob(s) in HEAD exceed 10 MiB."
        rem = "Use Git LFS or external storage for large binaries."
    else:
        status = "PASS"
        summary = "No blobs ≥ 10 MiB in the current HEAD tree. History-only blobs were not fully scanned."
        rem = None
    return _result(
        "R04",
        status=status,
        summary=summary,
        evidence={"counts": {"over_10mib": len(current), "over_50mib": len(huge)}, "paths": paths, "sizes": sizes},
        evidence_flags={"observed": True},
        data_quality={"complete": False, "missing_sources": ["full_blob_history"]},
        remediation=rem,
    )


def check_r05(ctx: RepoContext) -> dict:
    flagged = []
    for p in ctx.tracked:
        name = Path(p).name.lower()
        if name == ".env.example" or name.endswith(".env.example"):
            continue
        if ARTIFACT_NAME_RE.search(p.replace("\\", "/")) or ARTIFACT_DIR_RE.search(p.replace("\\", "/")):
            flagged.append(p)
        elif looks_like_credential(p):
            flagged.append(p)
    if flagged:
        return _result(
            "R05",
            status="FAIL",
            summary=f"{len(flagged)} tracked path(s) look like dumps, caches, logs, or credentials.",
            evidence={"paths": flagged[:50], "counts": {"flagged": len(flagged)}},
            evidence_flags={"observed": True},
            remediation="Untrack the files, add .gitignore rules, and rotate any real secrets (R05 does not remove history).",
        )
    has_ignore = _find_root(ctx, [".gitignore"]) is not None
    extra = " .gitignore is present." if has_ignore else " No .gitignore at repo root (does not fail this check)."
    return _result(
        "R05",
        status="PASS",
        summary=f"No obvious artifact/credential filenames in tracked files.{extra}",
        evidence={"paths": [".gitignore"] if has_ignore else []},
        evidence_flags={"declared": has_ignore, "observed": True},
    )


def check_r06(ctx: RepoContext) -> dict:
    blobs = [t for t in ctx.tree if t["kind"] == "blob"]
    total = len(blobs) or 1
    total_bytes = sum(t["size"] for t in blobs) or 1
    gen = [t for t in blobs if _is_generated(t["path"])]
    binary = [t for t in blobs if _is_binary_path(t["path"], t["size"])]
    gen_b = sum(t["size"] for t in gen)
    bin_b = sum(t["size"] for t in binary)
    return _result(
        "R06",
        status=None,
        summary=(
            f"Generated paths {len(gen)}/{len(blobs)} files ({gen_b / total_bytes:.0%} bytes); "
            f"binary {len(binary)}/{len(blobs)} ({bin_b / total_bytes:.0%} bytes)."
        ),
        observations={
            "files": len(blobs),
            "generated_files": len(gen),
            "binary_files": len(binary),
            "generated_bytes_ratio": round(gen_b / total_bytes, 4),
            "binary_bytes_ratio": round(bin_b / total_bytes, 4),
        },
        evidence={"counts": {"files": len(blobs), "generated": len(gen), "binary": len(binary)}},
        evidence_flags={"observed": True},
    )


def check_r07(ctx: RepoContext) -> dict:
    gm = _find_any(ctx, (".gitmodules",))
    gitlinks = [t for t in ctx.tree if t["kind"] == "commit" or t.get("mode") == "160000"]
    if not gm and not gitlinks:
        return _result(
            "R07",
            status="NOT_APPLICABLE",
            summary="No .gitmodules or gitlinks in HEAD.",
            evidence={"paths": []},
            reason_code="NOT_APPLICABLE",
        )
    status_text = git_cli.submodule_status(ctx.path)
    missing = []
    for line in status_text.splitlines():
        if line.startswith("-"):
            missing.append(line[1:].strip()[:200])
    if missing:
        return _result(
            "R07",
            status="FAIL",
            summary=f"{len(missing)} submodule gitlink(s) do not have a checked-out commit.",
            evidence={"paths": gm, "missing": missing[:20], "gitlinks": len(gitlinks)},
            evidence_flags={"declared": bool(gm), "observed": True},
            remediation="Init/sync submodules from allowed URLs, or remove stale gitlinks.",
            data_quality={"complete": True, "missing_sources": []},
        )
    return _result(
        "R07",
        status="WARN" if gm and not gitlinks else "PASS",
        summary="Submodule gitlinks are present; remote URL policy and fetchability were not verified.",
        evidence={"paths": gm, "gitlinks": [t["path"] for t in gitlinks][:20], "status_excerpt": status_text[:500]},
        evidence_flags={"declared": bool(gm), "configured": bool(gitlinks), "enforced": None, "observed": True},
        data_quality={"complete": False, "missing_sources": ["submodule_url_allowlist"]},
        remediation="Confirm submodule URLs are in the org allowlist and commits are reachable.",
    )


def check_r08(ctx: RepoContext) -> dict:
    loose = ctx.counts.get("count")
    packs = ctx.counts.get("packs")
    try:
        loose_n = int(str(loose).split()[0]) if loose is not None else 0
    except ValueError:
        loose_n = 0
    refs = git_cli.ref_count(ctx.path)
    return _result(
        "R08",
        status=None,
        summary=f"{loose_n} loose objects, {packs or '?'} pack(s), {refs} refs. Local figures do not describe server housekeeping.",
        observations={"loose_objects": loose_n, "packs": packs, "refs": refs, "loose_warn_threshold": LOOSE_WARN},
        evidence={"count_objects": ctx.counts, "ref_count": refs},
        evidence_flags={"observed": True},
        remediation="Consider git maintenance on clones with many loose objects; do not run it from the auditor.",
    )


# --- D ---

def _readme_path(ctx: RepoContext) -> str | None:
    return _find_root(ctx, ["README", "README.md", "README.rst", "README.txt"])


def check_d01(ctx: RepoContext) -> dict:
    path = _readme_path(ctx)
    if not path:
        return _result(
            "D01",
            status="FAIL",
            summary="No README at repo root.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add a README covering purpose, local run, tests, and owner.",
        )
    text = _read_text(ctx, path)
    missing = []
    if not _has_keywords(text, RUN_HINTS):
        missing.append("run/setup")
    if not _has_keywords(text, TEST_HINTS):
        missing.append("tests")
    if not _has_keywords(text, OWNER_HINTS):
        missing.append("owner/contact")
    if len(text.strip()) < 120:
        missing.append("substance")
    if missing:
        return _result(
            "D01",
            status="WARN",
            summary=f"README exists but looks thin on: {', '.join(missing)}.",
            evidence={"paths": [path], "missing_topics": missing},
            evidence_flags={"declared": True, "observed": True},
            remediation="Describe purpose, how to run and test, and who owns the repo.",
        )
    return _result(
        "D01",
        status="PASS",
        summary=f"Found {path} with run/test/owner-related content.",
        evidence={"paths": [path]},
        evidence_flags={"declared": True, "observed": True},
    )


def check_d02(ctx: RepoContext) -> dict:
    owners = _codeowners_path(ctx)
    maintainers = _find_any(ctx, ("MAINTAINERS.md", "MAINTAINERS", "OWNERS", "OWNERS.md"))
    catalog = _find_any(ctx, ("catalog-info.yaml", "catalog-info.yml", "service.yaml", "service.yml"))
    paths = [p for p in [owners, *maintainers, *catalog] if p]
    if not paths:
        return _result(
            "D02",
            status="FAIL",
            summary="No CODEOWNERS, MAINTAINERS, or service catalog file naming an owner.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add CODEOWNERS or MAINTAINERS.md with a living team/contact.",
        )
    return _result(
        "D02",
        status="PASS",
        summary=f"Ownership files present: {', '.join(paths)}.",
        evidence={"paths": paths},
        evidence_flags={"declared": True, "configured": True, "enforced": None},
        data_quality={"complete": False, "missing_sources": ["org_directory"]},
        remediation="Confirm named groups still exist in the org directory.",
    )


def check_d03(ctx: RepoContext) -> dict:
    path = _codeowners_path(ctx)
    if not path:
        return _result(
            "D03",
            status="FAIL",
            summary="No CODEOWNERS file; coverage is 0.",
            evidence={"paths": [], "counts": {"matched": 0, "tracked": len(ctx.tracked)}},
            evidence_flags={"declared": False},
            remediation="Add a CODEOWNERS file with path-specific owners, not only a repo-wide wildcard.",
        )
    rules = _parse_codeowners(_read_text(ctx, path))
    if not rules:
        return _result(
            "D03",
            status="FAIL",
            summary="CODEOWNERS exists but has no owner rules.",
            evidence={"paths": [path]},
            evidence_flags={"declared": True, "configured": False},
            remediation="Add path patterns with valid owners.",
        )
    production = [
        p for p in ctx.tracked
        if not _is_generated(p) and not p.startswith("docs/")
    ]
    denom = len(production) or 1
    matched = 0
    wildcard_only = all(pat in {"*", "**", "/*"} for pat, _, _ in rules)
    optional_only = all(opt for _, _, opt in rules)
    for p in production:
        if any(_codeowners_match(pat, p) for pat, _, _ in rules):
            matched += 1
    ratio = matched / denom
    if optional_only:
        status, summary = "WARN", "All CODEOWNERS sections are optional; matching is not required review."
    elif wildcard_only:
        status, summary = "WARN", f"Formal coverage {ratio:.0%} but only a wildcard rule — no path ownership split."
    elif ratio < 0.8:
        status, summary = "WARN", f"{ratio:.0%} of non-generated tracked files match a CODEOWNERS rule."
    else:
        status, summary = "PASS", f"{ratio:.0%} of non-generated tracked files match a CODEOWNERS rule."
    return _result(
        "D03",
        status=status,
        summary=summary,
        evidence={
            "paths": [path],
            "counts": {"matched": matched, "production_files": len(production), "rules": len(rules)},
        },
        observations={"coverage": round(ratio, 4), "wildcard_only": wildcard_only},
        evidence_flags={"declared": True, "configured": True, "enforced": None, "observed": True},
        data_quality={"complete": False, "missing_sources": ["gitlab_codeowners_dialect"]},
        remediation="Add owners for unmatched production paths; avoid a single '*' as the only rule.",
        score=ratio if status != "FAIL" else 0.0,
    )


def check_d04(ctx: RepoContext) -> dict:
    path = _find_root(ctx, ["CONTRIBUTING", "CONTRIBUTING.md"])
    if not path:
        extra = _find_any(ctx, ("docs/CONTRIBUTING.md", "docs/contributing.md"))
        path = extra[0] if extra else None
    if not path:
        return _result(
            "D04",
            status="FAIL",
            summary="No CONTRIBUTING guide at repo root or docs/.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add CONTRIBUTING.md (or link to the org standard) covering setup, checks, and MR flow.",
        )
    text = _read_text(ctx, path)
    ok = _has_keywords(text, ("merge request", "pull request", "mr ", "pr ")) and _has_keywords(text, ("test", "ci", "lint"))
    if not ok:
        return _result(
            "D04",
            status="WARN",
            summary=f"{path} exists but does not clearly describe MR flow and checks.",
            evidence={"paths": [path]},
            evidence_flags={"declared": True, "observed": True},
            remediation="Document setup, required checks, and how to open an MR.",
        )
    return _result(
        "D04",
        status="PASS",
        summary=f"Found {path} with contribution/MR guidance.",
        evidence={"paths": [path]},
        evidence_flags={"declared": True, "observed": True},
    )


def check_d05(ctx: RepoContext) -> dict:
    path = _find_root(ctx, ["SECURITY.md", "SECURITY"]) or (
        _find_any(ctx, ("docs/SECURITY.md", ".github/SECURITY.md")) or [None]
    )[0]
    if not path:
        return _result(
            "D05",
            status="WARN",
            summary="No SECURITY.md. Internal projects may rely on a corporate channel — that was not linked here.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add SECURITY.md or a README link to the org vulnerability-reporting process.",
        )
    text = _read_text(ctx, path)
    if len(text.strip()) < 40:
        return _result(
            "D05",
            status="WARN",
            summary=f"{path} is present but too short to describe a reporting channel.",
            evidence={"paths": [path]},
            evidence_flags={"declared": True},
            remediation="State how to report a vulnerability and who owns the response.",
        )
    return _result(
        "D05",
        status="PASS",
        summary=f"Found {path}.",
        evidence={"paths": [path]},
        evidence_flags={"declared": True, "observed": True},
    )


def check_d06(ctx: RepoContext) -> dict:
    paths = _find_any(
        ctx,
        (
            "RUNBOOK.md",
            "runbook.md",
            "docs/RUNBOOK.md",
            "docs/runbook.md",
            "docs/operations.md",
            "docs/ops.md",
            "OPERATIONS.md",
        ),
    )
    if not paths:
        readme = _readme_path(ctx)
        text = _read_text(ctx, readme) if readme else ""
        if readme and _has_keywords(text, DEPLOY_HINTS):
            return _result(
                "D06",
                status="WARN",
                summary="No dedicated runbook file; README mentions deploy/ops. External runbooks are UNKNOWN.",
                evidence={"paths": [readme]},
                evidence_flags={"declared": True, "observed": False},
                data_quality={"complete": False, "missing_sources": ["external_runbook"]},
                remediation="Add RUNBOOK.md or docs/operations.md (health, rollback, contacts) or link a catalog URL.",
            )
        return _result(
            "D06",
            status="FAIL",
            summary="No production runbook (RUNBOOK.md / docs/operations.md) in the tree.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Document diagnostics, health checks, rollback, and emergency contacts.",
        )
    text = _read_text(ctx, paths[0])
    missing = [k for k in ("rollback", "health", "alert", "dashboard") if k not in text.lower()]
    status = "WARN" if len(missing) >= 3 else "PASS"
    return _result(
        "D06",
        status=status,
        summary=f"Found {paths[0]}" + (f"; missing topics: {', '.join(missing)}." if status == "WARN" else "."),
        evidence={"paths": paths, "missing_topics": missing},
        evidence_flags={"declared": True, "observed": True},
        remediation="Cover health checks, dashboards, alerting, rollback, and contacts." if status == "WARN" else None,
    )


def check_d07(ctx: RepoContext) -> dict:
    paths = _find_any(
        ctx,
        (
            "docs/architecture.md",
            "ARCHITECTURE.md",
            "docs/ARCHITECTURE.md",
            "docs/adr/README.md",
            "adr/README.md",
        ),
    )
    adrs = [p for p in ctx.tracked if "/adr/" in p.lower() or p.lower().startswith("adr/")]
    if not paths and not adrs:
        return _result(
            "D07",
            status="WARN",
            summary="No architecture doc or ADR directory found.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add docs/architecture.md or ADRs for component boundaries and key decisions.",
        )
    return _result(
        "D07",
        status="PASS",
        summary="Architecture documentation or ADRs are present.",
        evidence={"paths": (paths + adrs)[:30]},
        evidence_flags={"declared": True, "observed": True},
    )


def check_d08(ctx: RepoContext) -> dict:
    path = _find_root(ctx, ["LICENSE", "LICENSE.md", "COPYING", "COPYING.md", "LICENSE.txt"])
    reuse = _find_any(ctx, ("LICENSE.spdx", ".reuse/dep5"))
    if not path and not reuse:
        return _result(
            "D08",
            status="WARN",
            summary="No LICENSE/COPYING file. For internal code a proprietary notice may live elsewhere.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add LICENSE or a corporate proprietary notice if required by policy.",
        )
    return _result(
        "D08",
        status="PASS",
        summary=f"License notice present ({path or ', '.join(reuse)}). Not a legal sufficiency review.",
        evidence={"paths": [p for p in [path, *reuse] if p]},
        evidence_flags={"declared": True},
    )


def check_d09(ctx: RepoContext) -> dict:
    hits = [
        p for p in ctx.tracked
        if p.lower().startswith(".gitlab/merge_request_templates/")
        or p.lower().startswith(".gitlab/issue_templates/")
        or p.lower().startswith(".github/pull_request_template")
        or p.lower().startswith(".github/ISSUE_TEMPLATE".lower())
        or Path(p).name.lower() in {"pull_request_template.md", "merge_request_template.md"}
    ]
    if not hits:
        return _result(
            "D09",
            status="WARN",
            summary="No MR/issue description templates found. Filled MR quality is a separate result.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add GitLab description templates covering intent, testing, risk, and rollback.",
        )
    return _result(
        "D09",
        status="PASS",
        summary=f"Found {len(hits)} MR/issue template file(s).",
        evidence={"paths": hits[:20]},
        evidence_flags={"declared": True, "observed": None},
    )


def check_d10(ctx: RepoContext) -> dict:
    paths = _find_any(ctx, ("catalog-info.yaml", "catalog-info.yml", "service.yaml", "service.yml"))
    if not paths:
        return _result(
            "D10",
            status="WARN",
            summary="No catalog-info.yaml / service.yaml service metadata.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add a Backstage/service descriptor with team, lifecycle, criticality, and ops links.",
        )
    text = _read_text(ctx, paths[0])
    missing = [k for k in ("owner", "lifecycle", "spec") if k not in text.lower()]
    status = "WARN" if missing == ["owner", "lifecycle", "spec"] else "PASS"
    return _result(
        "D10",
        status=status,
        summary=f"Found {paths[0]}.",
        evidence={"paths": paths},
        evidence_flags={"declared": True},
        data_quality={"complete": False, "missing_sources": ["service_catalog_sync"]},
    )


# --- G ---

def check_g01(ctx: RepoContext) -> dict:
    return _gitlab_unknown("G01", "protected default/release branches")


def check_g02(ctx: RepoContext) -> dict:
    return _gitlab_unknown("G02", "direct-push vs MR-only permissions")


def check_g03(ctx: RepoContext) -> dict:
    return _gitlab_unknown("G03", "independent approval settings")


def check_g04(ctx: RepoContext) -> dict:
    return _gitlab_unknown("G04", "approval reset after new commits")


def check_g05(ctx: RepoContext) -> dict:
    path = _codeowners_path(ctx)
    flags = {"declared": bool(path), "configured": None, "enforced": None, "observed": None}
    if not path:
        return _result(
            "G05",
            status="FAIL",
            summary="No CODEOWNERS file, so required owner review cannot be configured.",
            evidence={"paths": []},
            evidence_flags=flags,
            reason_code=None,
            remediation="Add CODEOWNERS and enable required code owner approvals on protected branches.",
        )
    return _unknown(
        "G05",
        "UNSUPPORTED_ADAPTER",
        "CODEOWNERS is declared, but GitLab required-owner-approval enforcement cannot be read from a clone.",
        missing=["gitlab_api"],
        remediation="Enable ‘Require approval from code owners’ and verify it via the Approvals API.",
    )


def check_g06(ctx: RepoContext) -> dict:
    ci = _ci_paths(ctx)
    if not ci:
        return _result(
            "G06",
            status="FAIL",
            summary="No CI config found, so required status checks cannot exist.",
            evidence={"paths": []},
            evidence_flags={"declared": False, "enforced": False},
            remediation="Add CI and require a successful pipeline to merge.",
        )
    return _unknown(
        "G06",
        "UNSUPPORTED_ADAPTER",
        "CI config is present; whether merge is blocked on a successful pipeline needs GitLab merge checks.",
        missing=["gitlab_api"],
        remediation="Require a successful pipeline for merge and reject skipped/allow_failure as a fake green.",
    )


def check_g07(ctx: RepoContext) -> dict:
    ci_paths = _ci_paths(ctx)
    extra = [p for p in ctx.tracked if Path(p).name.lower() in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"} or p.lower().endswith(".tf")]
    critical = ci_paths + extra
    owners = _codeowners_path(ctx)
    if not critical:
        return _result(
            "G07",
            status="NOT_APPLICABLE",
            summary="No CI/Dockerfile/IaC paths found to protect.",
            reason_code="NOT_APPLICABLE",
            evidence={"paths": []},
        )
    if not owners:
        return _result(
            "G07",
            status="FAIL",
            summary="CI/deploy files exist but there is no CODEOWNERS coverage for them.",
            evidence={"paths": critical[:20]},
            evidence_flags={"declared": False},
            remediation="Put CI, Dockerfiles, and IaC under CODEOWNERS with extra approvals.",
        )
    rules = _parse_codeowners(_read_text(ctx, owners))
    uncovered = [p for p in critical if not any(_codeowners_match(pat, p) for pat, _, opt in rules if not opt)]
    if uncovered:
        return _result(
            "G07",
            status="WARN",
            summary=f"{len(uncovered)} CI/deploy path(s) are not matched by a non-optional CODEOWNERS rule. Enforcement is UNKNOWN.",
            evidence={"paths": uncovered[:20], "codeowners": owners},
            evidence_flags={"declared": True, "configured": False, "enforced": None},
            remediation="Add CODEOWNERS rules for CI and deploy paths; require those approvals on the default branch.",
        )
    return _unknown(
        "G07",
        "UNSUPPORTED_ADAPTER",
        "CI paths match CODEOWNERS; whether those approvals are required still needs GitLab settings.",
        missing=["gitlab_api"],
        remediation="Require code-owner approval for CI/deploy paths and lock approval-rule edits in MRs.",
    )


def check_g08(ctx: RepoContext) -> dict:
    if not ctx.tags:
        return _result(
            "G08",
            status="NOT_APPLICABLE",
            summary="No git tags in this clone, so release-tag immutability is not applicable yet.",
            reason_code="NOT_APPLICABLE",
            evidence={"counts": {"tags": 0}},
        )
    return _unknown(
        "G08",
        "UNSUPPORTED_ADAPTER",
        f"{len(ctx.tags)} tag(s) found; protected-tag permissions and retarget history need the GitLab API.",
        missing=["gitlab_api"],
        remediation="Protect release tags and audit retarget/delete events; a boolean ‘protected’ is not enough.",
    )


def check_g09(ctx: RepoContext) -> dict:
    stats = git_cli.signature_stats(ctx.path, 300)
    scanned = stats["scanned"]
    good = stats["good"]
    if scanned == 0:
        return _result(
            "G09",
            status="UNKNOWN",
            summary="No commits to inspect for signatures.",
            reason_code="NO_EVENTS_IN_WINDOW",
            evidence=stats,
        )
    ratio = good / scanned
    emails = {_identity(c).split("@")[-1] for c in ctx.commits if "@" in _identity(c)}
    summary = f"{good}/{scanned} sampled commits have a good signature (git %G?=G). Email domains: {', '.join(sorted(emails)[:6]) or 'n/a'}."
    if good == 0:
        status = "WARN"
        rem = "Signing is not in use on HEAD history. Push rules and a trust policy are still UNKNOWN without GitLab."
    else:
        status = "PASS" if ratio >= 0.8 else "WARN"
        rem = "Define a trust policy for signer identities; a valid signature is not authorship by itself."
    return _result(
        "G09",
        status=status,
        summary=summary,
        evidence={"signature": stats, "email_domains": sorted(emails)[:20]},
        observations={"good_signature_ratio": round(ratio, 4)},
        evidence_flags={"observed": True, "enforced": None},
        data_quality={"complete": False, "missing_sources": ["gitlab_push_rules", "trust_policy"]},
        remediation=rem,
        score=ratio,
    )


def check_g10(ctx: RepoContext) -> dict:
    if not ctx.commits:
        return _result("G10", status="UNKNOWN", summary="No commits to inspect.", reason_code="NO_EVENTS_IN_WINDOW")
    linked = 0
    weak = []
    for c in ctx.commits:
        if ISSUE_REF_RE.search(c.get("subject") or ""):
            linked += 1
        elif len(weak) < 8:
            weak.append({"sha": c["sha"], "subject": c["subject"]})
    ratio = linked / len(ctx.commits)
    status = "PASS" if ratio >= 0.5 else "WARN"
    return _result(
        "G10",
        status=status,
        summary=f"{linked}/{len(ctx.commits)} commit subjects reference an issue/URL. MR descriptions were not available.",
        evidence={"counts": {"linked": linked, "scanned": len(ctx.commits)}, "commits": weak},
        observations={"subject_link_ratio": round(ratio, 4)},
        evidence_flags={"observed": True},
        data_quality={"complete": False, "missing_sources": ["merge_request_descriptions"]},
        remediation="Require a real issue/incident/rationale on MRs; a dangling ticket id is not enough.",
        score=ratio,
    )


def check_g11(ctx: RepoContext) -> dict:
    merges, total = git_cli.merge_commit_count(ctx.path, 400)
    if total == 0:
        return _result("G11", status=None, summary="No commits to classify merge strategy.")
    ratio = merges / total
    contrib = _find_root(ctx, ["CONTRIBUTING", "CONTRIBUTING.md"])
    return _result(
        "G11",
        status=None,
        summary=f"{merges}/{total} sampled commits are merge commits ({ratio:.0%}). Policy vs GitLab squash setting was not read.",
        observations={"merge_commit_ratio": round(ratio, 4), "sampled": total},
        evidence={"paths": [contrib] if contrib else [], "counts": {"merges": merges, "sampled": total}},
        evidence_flags={"observed": True, "configured": None},
    )


def check_g12(ctx: RepoContext) -> dict:
    branches = [b for b in ctx.remote_branches if not b["name"].endswith("/HEAD")]
    stale = []
    cutoff = ctx.now - STALE_BRANCH_DAYS * DAY
    for b in branches:
        short = b["name"].split("/", 1)[-1]
        if short in {ctx.default_branch, "main", "master", "develop", "release"}:
            continue
        if b["timestamp"] and b["timestamp"] < cutoff:
            stale.append(b["name"])
    return _result(
        "G12",
        status=None,
        summary=f"{len(stale)} remote branch(es) older than {STALE_BRANCH_DAYS} days (excluding likely long-lived names).",
        observations={"stale_branches": len(stale), "remote_branches": len(branches), "window_days": STALE_BRANCH_DAYS},
        evidence={"samples": stale[:30]},
        evidence_flags={"observed": True},
        remediation="Ask owners to delete merged/inactive branches; keep release/support branches.",
    )


# --- Q ---

def check_q01(ctx: RepoContext) -> dict:
    ci = _ci_paths(ctx)
    if not ci:
        return _result(
            "Q01",
            status="FAIL",
            summary="No CI configuration, so MR pipelines cannot be running.",
            evidence={"paths": []},
            evidence_flags={"declared": False, "observed": False},
            remediation="Add CI and ensure it runs on every eligible MR revision.",
        )
    return _unknown(
        "Q01",
        "UNSUPPORTED_ADAPTER",
        f"CI config present ({ci[0]}); YAML is not proof that pipelines ran on each MR SHA.",
        missing=["gitlab_api"],
        remediation="Measure the share of MRs with a pipeline on the reviewed SHA.",
    )


def check_q02(ctx: RepoContext) -> dict:
    tests = [p for p in ctx.tracked if _is_test_path(p)]
    if not tests:
        return _result(
            "Q02",
            status="FAIL",
            summary="No conventional test files found, so required tests cannot have run.",
            evidence={"counts": {"test_files": 0}, "paths": []},
            evidence_flags={"declared": False, "observed": False},
            remediation="Add automated tests and publish a machine-readable report from CI.",
        )
    junit = [p for p in ctx.tracked if "junit" in p.lower() or p.lower().endswith("test-results.xml")]
    return _unknown(
        "Q02",
        "EXPIRED_ARTIFACT" if not junit else "UNSUPPORTED_ADAPTER",
        f"{len(tests)} test file(s) exist; CI execution and JUnit results were not available in this clone.",
        missing=["ci_artifacts"],
        remediation="Publish JUnit (or equivalent) from CI. An empty report or a job named ‘test’ is not a PASS.",
    )


def check_q03(ctx: RepoContext) -> dict:
    return _gitlab_unknown("Q03", "default-branch pipeline status")


def check_q04(ctx: RepoContext) -> dict:
    cov = [
        p for p in ctx.tracked
        if Path(p).name.lower() in {"coverage.xml", "cobertura.xml", "lcov.info"}
        or "/coverage/" in p.lower()
    ]
    return _result(
        "Q04",
        status=None,
        summary=(
            f"Found {len(cov)} coverage artifact path(s) in git. Live CI coverage and diff-cover were not read."
            if cov
            else "No coverage artifacts tracked. Whether CI publishes coverage is UNKNOWN."
        ),
        observations={"tracked_coverage_files": len(cov)},
        evidence={"paths": cov[:20]},
        evidence_flags={"declared": bool(cov), "observed": False},
        data_quality={"complete": False, "missing_sources": ["ci_artifacts"]},
    )


def check_q05(ctx: RepoContext) -> dict:
    return _unknown(
        "Q05",
        "UNSUPPORTED_ADAPTER",
        "Flaky-test rate needs test-case history across comparable revisions; job retries in this clone are not available.",
        missing=["ci_artifacts"],
        remediation="Store JUnit per revision and environment; do not treat a retried job as a proven flake.",
    )


def _config_present(ctx: RepoContext, names: tuple[str, ...], substrings: tuple[str, ...] = ()) -> list[str]:
    hits = []
    lower_map = {p.lower(): p for p in ctx.tracked}
    for n in names:
        if n.lower() in lower_map:
            hits.append(lower_map[n.lower()])
        elif (ctx.path / n).is_file():
            hits.append(n)
    for p in ctx.tracked:
        lp = p.lower()
        if any(s in lp for s in substrings):
            hits.append(p)
    seen = []
    for h in hits:
        if h not in seen:
            seen.append(h)
    return seen


def check_q06(ctx: RepoContext) -> dict:
    paths = _config_present(
        ctx,
        (".pre-commit-config.yaml", ".pre-commit-config.yml", ".eslintrc.json", ".eslintrc.cjs", "ruff.toml", ".ruff.toml", ".flake8", ".pylintrc"),
        ("eslint.config", "/ruff.toml", "prettier", ".golangci."),
    )
    if not paths:
        return _result(
            "Q06",
            status="FAIL",
            summary="No linter/formatter config found (pre-commit, ruff, eslint, …).",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add a linter/formatter and fail CI when it fails. A local hook alone is not enforcement.",
        )
    ci = _ci_paths(ctx)
    status = "WARN" if not ci else "PASS"
    extra = " CI config exists so enforcement is plausible but not proven." if ci else " No CI config — local-only."
    return _result(
        "Q06",
        status=status,
        summary=f"Found {paths[0]}.{extra}",
        evidence={"paths": paths[:15] + ci[:5]},
        evidence_flags={"declared": True, "enforced": None, "observed": False},
        remediation="Run the same linters in CI as required checks." if status == "WARN" else None,
    )


def check_q07(ctx: RepoContext) -> dict:
    paths = _config_present(
        ctx,
        ("mypy.ini", "pyrightconfig.json", "tsconfig.json", "tsconfig.app.json"),
        ("mypy.ini", "setup.cfg"),
    )
    py = any(p.endswith(".py") for p in ctx.tracked)
    ts = any(p.endswith((".ts", ".tsx")) for p in ctx.tracked)
    go = any(p.endswith(".go") for p in ctx.tracked)
    if not (py or ts or go):
        return _result(
            "Q07",
            status="NOT_APPLICABLE",
            summary="No Python/TypeScript/Go sources detected for type/static checks.",
            reason_code="NOT_APPLICABLE",
            evidence={"paths": []},
        )
    if ts and not any("tsconfig" in p.lower() for p in paths + ctx.tracked):
        return _result(
            "Q07",
            status="WARN",
            summary="TypeScript files exist without a tsconfig in view.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add tsconfig and run tsc (or equivalent) in CI.",
        )
    if py and not any("mypy" in p.lower() or "pyright" in p.lower() for p in ctx.tracked + paths):
        return _result(
            "Q07",
            status="WARN",
            summary="Python files exist without mypy/pyright config.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add a type checker and keep ignore lists from hiding missing coverage.",
        )
    return _result(
        "Q07",
        status="PASS",
        summary="Type/static-check config is present for the detected languages. CI execution was not verified.",
        evidence={"paths": paths[:15]},
        evidence_flags={"declared": True, "observed": False},
    )


def check_q08(ctx: RepoContext) -> dict:
    paths = [
        p for p in ctx.tracked
        if "semgrep" in p.lower()
        or "codeql" in p.lower()
        or p.lower() in {".gitlab-ci.yml"}
        or "sast" in p.lower()
        or p.lower().endswith("semgrep.yml")
    ]
    ci_text = ""
    for p in _ci_paths(ctx)[:3]:
        ci_text += _read_text(ctx, p)
    declared = bool(paths) or bool(re.search(r"sast|semgrep|codeql|bandit", ci_text, re.I))
    if not declared:
        return _result(
            "Q08",
            status="FAIL",
            summary="No SAST config or CI job names detected.",
            evidence={"paths": []},
            evidence_flags={"declared": False, "observed": False},
            remediation="Run Semgrep/CodeQL/GitLab SAST on the relevant code with fresh rules.",
        )
    return _unknown(
        "Q08",
        "UNSUPPORTED_ADAPTER",
        "SAST appears in config; a config without a successful recent scan is not a working control.",
        missing=["ci_artifacts"],
        remediation="Confirm the scanner ran on the current code with current rules and that findings are triaged.",
    )


def check_q09(ctx: RepoContext) -> dict:
    src = [t for t in ctx.tree if Path(t["path"]).suffix.lower() in SOURCE_EXTENSIONS and not _is_generated(t["path"])]
    large = sorted([t for t in src if t["size"] > 80_000], key=lambda x: -x["size"])[:15]
    return _result(
        "Q09",
        status=None,
        summary=f"{len(large)} source file(s) over 80 KiB (size proxy only; not cyclomatic complexity).",
        observations={"large_source_files": len(large), "source_files": len(src)},
        evidence={"paths": [t["path"] for t in large], "sizes": {t["path"]: t["size"] for t in large}},
        evidence_flags={"observed": True},
        data_quality={"complete": False, "missing_sources": ["complexity_engine"]},
    )


def check_q10(ctx: RepoContext) -> dict:
    return _unknown(
        "Q10",
        "UNSUPPORTED_ADAPTER",
        "CI feedback time needs pipeline/job timestamps and queue vs execution split.",
        missing=["gitlab_api"],
    )


# --- S ---

def check_s01(ctx: RepoContext) -> dict:
    name_hits = [p for p in ctx.tracked if looks_like_credential(p)]
    content_hits: list[str] = []
    scanned = 0
    for p in ctx.tracked:
        if _is_generated(p) or _is_binary_path(p):
            continue
        if Path(p).suffix.lower() not in {".py", ".ts", ".js", ".yml", ".yaml", ".json", ".env", ".toml", ".sh", ".tf", ""}:
            if Path(p).suffix.lower() not in {".md", ".txt", ".xml", ".properties", ".ini", ".cfg"}:
                continue
        scanned += 1
        if scanned > 400:
            break
        try:
            raw = (ctx.path / p).read_bytes()[:20_000]
        except OSError:
            continue
        if b"\0" in raw[:2048]:
            continue
        text = raw.decode("utf-8", "replace")
        if SECRET_CONTENT_RE.search(text):
            content_hits.append(p)
    if name_hits or content_hits:
        return _result(
            "S01",
            status="FAIL",
            summary=f"Secret-like filenames={len(name_hits)}, content matches={len(content_hits)} in the current tree (values redacted).",
            evidence={"paths": (name_hits + content_hits)[:50], "counts": {"filename": len(name_hits), "content": len(content_hits)}},
            evidence_flags={"observed": True},
            data_quality={"complete": False, "missing_sources": ["full_history_secret_scan"]},
            remediation="Rotate and revoke confirmed secrets, then remove them from history. Do not treat deleting the file as enough.",
        )
    return _result(
        "S01",
        status="WARN",
        summary="No obvious secrets in the sampled current tree. History-wide gitleaks and push protection are separate.",
        evidence={"counts": {"files_sampled": scanned}},
        evidence_flags={"observed": True, "enforced": None},
        data_quality={"complete": False, "missing_sources": ["full_history_secret_scan", "gitleaks"]},
        remediation="Run a dedicated secret scanner on reachable refs; a clean sample is not proof of no secrets.",
    )


def check_s02(ctx: RepoContext) -> dict:
    return _unknown(
        "S02",
        "UNSUPPORTED_ADAPTER",
        "Push secret protection is a server-side control. CI-after-push and local hooks are not equivalent.",
        missing=["gitlab_api"],
        remediation="Enable GitLab secret push protection (or a managed pre-receive scanner) with a tight allowlist.",
    )


def check_s03(ctx: RepoContext) -> dict:
    locks = [p for p in ctx.tracked if Path(p).name.lower() in LOCKFILES or Path(p).name.lower() in MANIFESTS]
    if not locks:
        return _result(
            "S03",
            status="NOT_APPLICABLE",
            summary="No language manifests/lockfiles found to scan.",
            reason_code="NOT_APPLICABLE",
            evidence={"paths": []},
        )
    return _unknown(
        "S03",
        "UNSUPPORTED_ADAPTER",
        f"Manifests present ({locks[0]}); no OSV/Trivy/GitLab dependency scan was executed in this run.",
        missing=["vulnerability_scanner"],
        remediation="Run OSV-Scanner/Trivy/GitLab Dependency Scanning on a schedule and fail SLA-overdue criticals.",
    )


def check_s04(ctx: RepoContext) -> dict:
    paths = _find_any(ctx, UPDATE_CONFIGS)
    if not paths:
        more = [p for p in ctx.tracked if "renovate" in p.lower() or "dependabot" in p.lower()]
        paths = more[:5]
    if not paths:
        return _result(
            "S04",
            status="FAIL",
            summary="No Renovate/Dependabot (or equivalent) config found.",
            evidence={"paths": []},
            evidence_flags={"declared": False, "observed": False},
            remediation="Enable dependency-update automation and actually merge the resulting MRs.",
        )
    return _unknown(
        "S04",
        "UNSUPPORTED_ADAPTER",
        f"Update config present ({paths[0]}); config without recent update MRs is not sufficient.",
        missing=["gitlab_api"],
        remediation="Confirm the bot runs on a schedule and the update queue is processed.",
    )


def check_s05(ctx: RepoContext) -> dict:
    return _unknown(
        "S05",
        "UNSUPPORTED_ADAPTER",
        "Dependency age/EOL needs package-registry metadata; a high major number is not by itself a violation.",
        missing=["registry"],
    )


def check_s06(ctx: RepoContext) -> dict:
    manifests = [p for p in ctx.tracked if Path(p).name.lower() in MANIFESTS]
    locks = [p for p in ctx.tracked if Path(p).name.lower() in LOCKFILES]
    go_mod = any(Path(p).name.lower() == "go.mod" for p in ctx.tracked)
    go_sum = any(Path(p).name.lower() == "go.sum" for p in ctx.tracked)
    if not manifests:
        return _result(
            "S06",
            status="NOT_APPLICABLE",
            summary="No application manifests; lockfile policy does not apply.",
            reason_code="NOT_APPLICABLE",
            evidence={"paths": []},
        )
    if go_mod and not go_sum:
        return _result(
            "S06",
            status="WARN",
            summary="go.mod is present without go.sum. go.sum is checksums, not a lockfile; still expected in apps.",
            evidence={"paths": [p for p in ctx.tracked if Path(p).name.lower() in {"go.mod", "go.sum"}]},
            evidence_flags={"declared": True, "configured": False},
            remediation="Commit go.sum and build with a frozen module graph in CI.",
        )
    npm = any(Path(p).name.lower() == "package.json" for p in manifests)
    npm_lock = any(Path(p).name.lower() in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"} for p in locks)
    py = any(Path(p).name.lower() in {"pyproject.toml", "pipfile", "requirements.txt"} for p in manifests)
    py_lock = any(Path(p).name.lower() in {"uv.lock", "poetry.lock", "pipfile.lock"} for p in locks)
    missing = []
    if npm and not npm_lock:
        missing.append("js lockfile")
    if py and not py_lock and not any(Path(p).name.lower() == "requirements.txt" for p in manifests):
        missing.append("python lockfile")
    if missing:
        return _result(
            "S06",
            status="FAIL",
            summary=f"Application manifests without frozen resolution: {', '.join(missing)}.",
            evidence={"paths": manifests[:10] + locks[:10]},
            evidence_flags={"declared": True, "configured": False},
            remediation="Commit lockfiles and use npm ci / uv sync --frozen / equivalent in CI.",
        )
    return _result(
        "S06",
        status="PASS",
        summary="Lock/pin files are present for detected ecosystems. CI frozen-install mode was not executed.",
        evidence={"paths": (manifests + locks)[:20]},
        evidence_flags={"declared": True, "configured": True, "observed": False},
    )


def _unpinned_from_text(text: str, path: str) -> list[str]:
    hits = []
    for m in re.finditer(r"uses:\s*([^\s#]+)", text):
        ref = m.group(1).strip().strip("'\"")
        if "@" not in ref:
            continue
        _, spec = ref.rsplit("@", 1)
        if not PINNED_SHA_RE.match(spec):
            hits.append(f"{path}: uses {ref}")
    for m in re.finditer(r"image:\s*([^\s#]+)", text, re.I):
        img = m.group(1).strip().strip("'\"")
        if img.startswith("$"):
            continue
        if IMAGE_DIGEST_RE.search(img):
            continue
        if img.endswith(":latest") or ":" not in img.split("/")[-1]:
            hits.append(f"{path}: image {img}")
    for m in re.finditer(r"include:\s*\n((?:\s+.+\n)+)", text):
        block = m.group(1)
        if re.search(r"ref:\s*main\b|ref:\s*master\b|file:\s*http", block, re.I):
            hits.append(f"{path}: mutable include ref")
    return hits


def check_s07(ctx: RepoContext) -> dict:
    files = _ci_paths(ctx)
    files += [p for p in ctx.tracked if p.lower().startswith(".github/actions/")]
    if not files:
        return _result(
            "S07",
            status="NOT_APPLICABLE",
            summary="No CI workflow/config files to pin.",
            reason_code="NOT_APPLICABLE",
            evidence={"paths": []},
        )
    mutable = []
    for p in files[:30]:
        mutable.extend(_unpinned_from_text(_read_text(ctx, p, 200_000), p))
    if mutable:
        return _result(
            "S07",
            status="FAIL",
            summary=f"{len(mutable)} mutable CI action/image/include pin(s) (tags/latest/main).",
            evidence={"paths": files[:15], "samples": mutable[:25]},
            evidence_flags={"declared": True, "configured": False},
            remediation="Pin actions to a 40-char SHA and images to digest; manage pin updates on purpose.",
        )
    return _result(
        "S07",
        status="PASS",
        summary="No obvious unpinned uses:/image:latest in sampled CI files.",
        evidence={"paths": files[:15]},
        evidence_flags={"declared": True, "configured": True},
    )


def check_s08(ctx: RepoContext) -> dict:
    workflows = [p for p in ctx.tracked if p.lower().startswith(".github/workflows/")]
    if workflows:
        broad = []
        for p in workflows[:20]:
            text = _read_text(ctx, p)
            if re.search(r"permissions:\s*\n\s+contents:\s+write", text) or re.search(r"permissions:\s+write-all", text):
                broad.append(p)
        if broad:
            return _result(
                "S08",
                status="WARN",
                summary=f"{len(broad)} GitHub workflow(s) request write/write-all permissions. GitLab job tokens were not read.",
                evidence={"paths": broad},
                evidence_flags={"declared": True, "configured": False, "enforced": None},
                data_quality={"complete": False, "missing_sources": ["gitlab_job_token"]},
                remediation="Set least-privilege permissions per job; never read secret values to prove this.",
            )
        return _result(
            "S08",
            status="WARN",
            summary="GitHub workflows found; token/permission review is partial. GitLab job-token allowlists need the API.",
            evidence={"paths": workflows[:10]},
            evidence_flags={"declared": True, "enforced": None},
            data_quality={"complete": False, "missing_sources": ["gitlab_api"]},
        )
    if _ci_paths(ctx):
        return _unknown(
            "S08",
            "UNSUPPORTED_ADAPTER",
            "GitLab job tokens, protected variables, and runner access cannot be read without the API (and must not dump secret values).",
            missing=["gitlab_api"],
        )
    return _result(
        "S08",
        status="NOT_APPLICABLE",
        summary="No CI config to inspect for token permissions.",
        reason_code="NOT_APPLICABLE",
    )


def check_s09(ctx: RepoContext) -> dict:
    files = _ci_paths(ctx)
    if not files:
        return _result("S09", status="NOT_APPLICABLE", summary="No CI workflows to inspect.", reason_code="NOT_APPLICABLE")
    findings = []
    for p in files[:25]:
        text = _read_text(ctx, p, 200_000)
        if re.search(r"pull_request_target", text):
            findings.append(f"{p}: pull_request_target")
        if re.search(r"privileged:\s*true", text):
            findings.append(f"{p}: privileged: true")
        if re.search(r"docker\.sock", text):
            findings.append(f"{p}: docker.sock")
        if re.search(r"include:\s*.*remote:", text) or re.search(r"include:\s*\n\s+-\s+remote:", text):
            findings.append(f"{p}: include remote")
        if re.search(r"CI_MERGE_REQUEST_SOURCE_BRANCH_NAME.*\|", text):
            findings.append(f"{p}: untrusted MR input interpolation")
    if findings:
        return _result(
            "S09",
            status="FAIL",
            summary=f"{len(findings)} dangerous CI trust-boundary pattern(s) in config.",
            evidence={"paths": files[:10], "samples": findings[:20]},
            evidence_flags={"declared": True, "configured": True, "observed": True},
            remediation="Keep untrusted MR code off privileged runners, caches, and secrets.",
        )
    return _result(
        "S09",
        status="PASS",
        summary="No pull_request_target / privileged / docker.sock / remote include patterns in sampled CI files.",
        evidence={"paths": files[:10]},
        evidence_flags={"declared": True, "observed": True, "enforced": None},
        data_quality={"complete": False, "missing_sources": ["runtime_runner_config"]},
    )


def check_s10(ctx: RepoContext) -> dict:
    files = [
        p for p in ctx.tracked
        if Path(p).name.lower() in SBOM_NAMES or "cyclonedx" in p.lower() or p.lower().endswith(".spdx.json")
    ]
    ci = "\n".join(_read_text(ctx, p) for p in _ci_paths(ctx)[:4])
    declared = bool(files) or bool(re.search(r"syft|cyclonedx|spdx|sbom", ci, re.I))
    if not declared:
        return _result(
            "S10",
            status="WARN",
            summary="No SBOM file or CI job mention found. An old source SBOM would not prove a release anyway.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Generate an SBOM bound to the artifact digest (Syft/CycloneDX/SPDX).",
        )
    return _result(
        "S10",
        status="WARN",
        summary="SBOM-related files/jobs exist; binding to a release digest was not verified.",
        evidence={"paths": files[:15]},
        evidence_flags={"declared": True, "observed": False},
        remediation="Attach the SBOM to the artifact digest you actually ship.",
    )


def check_s11(ctx: RepoContext) -> dict:
    stats = git_cli.signature_stats(ctx.path, 80)
    tags = ctx.tags
    return _unknown(
        "S11",
        "UNSUPPORTED_ADAPTER",
        f"Signed Git tags/commits (good signatures {stats['good']}/{stats['scanned']}) do not prove a signed binary artifact. Cosign/registry verify needs release artifacts.",
        missing=["registry"],
        remediation="Sign release digests and verify against a named identity/key policy.",
    )


def check_s12(ctx: RepoContext) -> dict:
    files = [p for p in ctx.tracked if "provenance" in p.lower() or "slsa" in p.lower() or p.lower().endswith(".intoto.jsonl")]
    if files:
        return _result(
            "S12",
            status="WARN",
            summary="Provenance-like files exist in git; a JSON file is not a verified attestation against a trust policy.",
            evidence={"paths": files[:15]},
            evidence_flags={"declared": True, "observed": False},
            remediation="Verify SLSA provenance for the shipped digest with a policy evaluator.",
        )
    return _unknown(
        "S12",
        "UNSUPPORTED_ADAPTER",
        "No in-repo provenance files. Verifying builder identity requires registry/attestation storage.",
        missing=["registry"],
        remediation="Produce and verify SLSA provenance v1.2 for production artifacts.",
    )


# --- L ---

def check_l01(ctx: RepoContext) -> dict:
    return _unknown(
        "L01",
        "UNSUPPORTED_ADAPTER",
        "Reproducible builds require isolated rebuilds and hash comparison. Lockfiles are only a prerequisite (see S06).",
        missing=["isolated_builder"],
        remediation="Document inputs, pin the builder, and compare hashes (or a stated normalization rule).",
    )


def check_l02(ctx: RepoContext) -> dict:
    return _unknown(
        "L02",
        "UNSUPPORTED_ADAPTER",
        "Production deploy → commit/pipeline/digest mapping needs deployment and registry metadata.",
        missing=["deployments"],
        remediation="Record service, environment, commit, pipeline, and artifact digest on each production deploy.",
    )


def check_l03(ctx: RepoContext) -> dict:
    pkg = None
    version = None
    if (ctx.path / "package.json").is_file():
        pkg = "package.json"
        m = re.search(r'"version"\s*:\s*"([^"]+)"', _read_text(ctx, "package.json"))
        version = m.group(1) if m else None
    elif (ctx.path / "pyproject.toml").is_file():
        pkg = "pyproject.toml"
        m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', _read_text(ctx, "pyproject.toml"))
        version = m.group(1) if m else None
    if not version:
        return _result(
            "L03",
            status="NOT_APPLICABLE",
            summary="No package version field found to compare with tags.",
            reason_code="NOT_APPLICABLE",
            evidence={"paths": []},
        )
    tag_hit = any(version in t for t in ctx.tags) or any(t.lstrip("v") == version for t in ctx.tags)
    if ctx.tags and not tag_hit:
        return _result(
            "L03",
            status="WARN",
            summary=f"Manifest version {version} does not match any git tag.",
            evidence={"paths": [pkg], "samples": ctx.tags[:20], "counts": {"tags": len(ctx.tags)}},
            evidence_flags={"declared": True, "observed": True},
            remediation="Keep package version, release metadata, and tags consistent — or document commit-based versioning.",
        )
    return _result(
        "L03",
        status="PASS" if tag_hit or not ctx.tags else "WARN",
        summary=f"Manifest version {version}" + (" matches a tag." if tag_hit else "; no tags to compare."),
        evidence={"paths": [pkg], "samples": ctx.tags[:15]},
        evidence_flags={"declared": True, "observed": True},
    )


def check_l04(ctx: RepoContext) -> dict:
    paths = _find_any(ctx, ("CHANGELOG.md", "CHANGES.md", "HISTORY.md", "docs/CHANGELOG.md"))
    if not paths:
        return _result(
            "L04",
            status="WARN",
            summary="No CHANGELOG. GitLab Releases were not queried.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            data_quality={"complete": False, "missing_sources": ["gitlab_releases"]},
            remediation="Publish human-readable notes with migrations and breaking changes — not only a commit dump.",
        )
    text = _read_text(ctx, paths[0])
    status = "PASS" if len(text.strip()) > 80 else "WARN"
    return _result(
        "L04",
        status=status,
        summary=f"Found {paths[0]}.",
        evidence={"paths": paths},
        evidence_flags={"declared": True, "observed": True},
    )


def check_l05(ctx: RepoContext) -> dict:
    if not ctx.commits:
        return _result("L05", status=None, summary="No commits to score against Conventional Commits.")
    good = sum(1 for c in ctx.commits if CONVENTIONAL_RE.match((c.get("subject") or "").strip()))
    ratio = good / len(ctx.commits)
    return _result(
        "L05",
        status=None,
        summary=f"{good}/{len(ctx.commits)} HEAD commits match Conventional Commits. Not a code-quality signal.",
        observations={"conventional_ratio": round(ratio, 4), "scanned": len(ctx.commits)},
        evidence={"counts": {"good": good, "scanned": len(ctx.commits)}},
        evidence_flags={"observed": True},
    )


def check_l06(ctx: RepoContext) -> dict:
    cutoff = ctx.now - 90 * DAY
    # tags have no dates here; use commit volume as weak proxy plus tag count
    recent_commits = sum(1 for c in ctx.commits if c["timestamp"] >= cutoff)
    return _result(
        "L06",
        status=None,
        summary=f"{len(ctx.tags)} tag(s) total; {recent_commits} commit(s) in 90d. Tags, package releases, and prod deploys are different series.",
        observations={"tags": len(ctx.tags), "commits_90d": recent_commits, "window_days": 90},
        evidence={"samples": ctx.tags[:20], "counts": {"tags": len(ctx.tags), "commits_90d": recent_commits}},
        evidence_flags={"observed": True},
        data_quality={"complete": False, "missing_sources": ["gitlab_releases", "deployments"]},
    )


# --- T ---

def check_t01(ctx: RepoContext) -> dict:
    if not ctx.commits:
        return _result(
            "T01",
            status=None,
            summary="No commits on HEAD. That is a signal to investigate, not automatic abandonment.",
            observations={"age_days": None, "commits": 0},
        )
    age = max(0.0, (ctx.now - ctx.commits[0]["timestamp"]) / DAY)
    return _result(
        "T01",
        status=None,
        summary=f"HEAD is {age:.1f} days old; {len(ctx.commits)} commit(s) sampled. Releases/MR replies were not read.",
        observations={"age_days": round(age, 2), "commits_sampled": len(ctx.commits), "maintained_hint_days": MAINTAINED_DAYS},
        evidence={"commits": [{"sha": ctx.commits[0]["sha"], "subject": ctx.commits[0]["subject"]}]},
        evidence_flags={"observed": True},
        data_quality={"complete": False, "missing_sources": ["gitlab_api"]},
    )


def check_t02(ctx: RepoContext) -> dict:
    cutoff = ctx.now - ABSENCE_WINDOW_DAYS * DAY
    weights: dict[str, float] = {}
    for c in ctx.commits:
        if c["timestamp"] < cutoff:
            continue
        weights[_identity(c)] = weights.get(_identity(c), 0) + 1
    k = _absence_factor(weights)
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    return _result(
        "T02",
        status=None,
        summary=(
            f"Contributor absence factor k={k} on authored commits in {ABSENCE_WINDOW_DAYS}d "
            f"(CHAOSS 50% share). Reviewer series needs MR data."
            if k is not None
            else "No commits in the window; k is null."
        ),
        observations={"k": k, "unit": "authored_commits", "window_days": ABSENCE_WINDOW_DAYS, "people": len(weights)},
        evidence={"authors": [{"name": a, "commits": int(n)} for a, n in ranked[:15]]},
        evidence_flags={"observed": True},
    )


def check_t03(ctx: RepoContext) -> dict:
    owners = _codeowners_path(ctx)
    rules = _parse_codeowners(_read_text(ctx, owners)) if owners else []
    patterns = [pat for pat, _, _ in rules if pat not in {"*", "**"}][:30]
    cutoff = ctx.now - 365 * DAY / 2
    if not patterns:
        # treat top-level dirs as components
        patterns = sorted({p.split("/")[0] + "/*" for p in ctx.tracked if "/" in p and not p.startswith(".")})[:20]
    active = 0
    dual = 0
    details = []
    for pat in patterns:
        people: dict[str, int] = {}
        for c in ctx.name_log:
            if c["timestamp"] < cutoff:
                continue
            if any(fnmatch.fnmatch(f, pat) or f.startswith(pat.rstrip("*")) for f in c.get("files") or []):
                people[_identity(c)] = people.get(_identity(c), 0) + 1
        if sum(people.values()) == 0:
            continue
        active += 1
        if len(people) >= 2:
            dual += 1
        details.append({"path": pat, "people": len(people)})
    coverage = (dual / active) if active else None
    return _result(
        "T03",
        status=None,
        summary=(
            f"{dual}/{active} active path-components have ≥2 authors in ~6 months."
            if active
            else "No active components in the window."
        ),
        observations={"coverage": coverage, "active_components": active, "dual_owned": dual},
        evidence={"samples": details[:20], "paths": [owners] if owners else []},
        evidence_flags={"observed": True},
        data_quality={"complete": False, "missing_sources": ["mr_reviewers"]},
    )


def check_t04(ctx: RepoContext) -> dict:
    return _unknown("T04", "UNSUPPORTED_ADAPTER", "Review coverage needs merged-MR approval/review events.", missing=["gitlab_api"])


def check_t05(ctx: RepoContext) -> dict:
    return _unknown(
        "T05",
        "UNSUPPORTED_ADAPTER",
        "Author=merger is not a violation by itself; this check needs MR approval timelines.",
        missing=["gitlab_api"],
    )


def check_t06(ctx: RepoContext) -> dict:
    return _unknown("T06", "UNSUPPORTED_ADAPTER", "Time to first review needs MR timestamps and human review events.", missing=["gitlab_api"])


def check_t07(ctx: RepoContext) -> dict:
    return _unknown(
        "T07",
        "UNSUPPORTED_ADAPTER",
        "MR cycle time is merged_at − created_at on a merged-MR cohort. Open MRs belong in T08.",
        missing=["gitlab_api"],
    )


def check_t08(ctx: RepoContext) -> dict:
    return _unknown("T08", "UNSUPPORTED_ADAPTER", "Stale/WIP MRs need the open MR snapshot from GitLab.", missing=["gitlab_api"])


def check_t09(ctx: RepoContext) -> dict:
    cutoff = ctx.now - BATCH_WINDOW_DAYS * DAY
    sizes = [len(c.get("files") or []) for c in ctx.name_log if c["timestamp"] >= cutoff]
    if not sizes:
        return _result("T09", status=None, summary="No file-changing commits in the 90d window.")
    sizes_sorted = sorted(sizes)
    p50 = sizes_sorted[len(sizes_sorted) // 2]
    p85 = sizes_sorted[min(len(sizes_sorted) - 1, int(len(sizes_sorted) * 0.85))]
    return _result(
        "T09",
        status=None,
        summary=f"Files touched per commit in 90d: p50={p50}, p85={p85}, n={len(sizes)}. This is commit size, not MR diff size.",
        observations={"p50_files": p50, "p85_files": p85, "n": len(sizes), "unit": "commit_paths"},
        evidence={"counts": {"commits": len(sizes)}},
        evidence_flags={"observed": True},
        data_quality={"complete": False, "missing_sources": ["merge_request_diffs"]},
    )


def check_t10(ctx: RepoContext) -> dict:
    cutoff = ctx.now - 56 * DAY
    recent = [c for c in ctx.commits if c["timestamp"] >= cutoff]
    # bucket by iso week
    buckets: dict[str, int] = {}
    for c in recent:
        week = time.strftime("%G-W%V", time.gmtime(c["timestamp"]))
        buckets[week] = buckets.get(week, 0) + 1
    return _result(
        "T10",
        status=None,
        summary=f"{len(recent)} commit(s) in 8 weeks (commit proxy for merged-MR throughput).",
        observations={"commits_8w": len(recent), "weeks": buckets},
        evidence={"counts": {"commits_8w": len(recent)}},
        evidence_flags={"observed": True},
        data_quality={"complete": False, "missing_sources": ["merged_merge_requests"]},
    )


def check_t11(ctx: RepoContext) -> dict:
    cutoff_old = ctx.now - CHURN_WINDOW_DAYS * 2 * DAY
    mid = ctx.now - CHURN_WINDOW_DAYS * DAY
    first: set[str] = set()
    again: set[str] = set()
    for c in ctx.name_log:
        ts = c["timestamp"]
        files = [f for f in c.get("files") or [] if not _is_generated(f)]
        if cutoff_old <= ts < mid:
            first.update(files)
        elif ts >= mid:
            again.update(files)
    denom = len(first)
    num = len(first & again)
    ratio = (num / denom) if denom else None
    return _result(
        "T11",
        status=None,
        summary=(
            f"{num}/{denom} files changed in the prior {CHURN_WINDOW_DAYS}d were changed again in the last {CHURN_WINDOW_DAYS}d."
            if denom
            else "Not enough history in the churn windows."
        ),
        observations={"file_churn_ratio": ratio, "window_days": CHURN_WINDOW_DAYS, "unit": "files_not_lines"},
        evidence={"counts": {"prior_files": denom, "rechanged": num}},
        evidence_flags={"observed": True},
        data_quality={"complete": False, "missing_sources": ["line_level_blame"]},
    )


def check_t12(ctx: RepoContext) -> dict:
    cutoff = ctx.now - HOTSPOT_WINDOW_DAYS * DAY
    freq: dict[str, int] = {}
    authors: dict[str, set[str]] = {}
    for c in ctx.name_log:
        if c["timestamp"] < cutoff:
            continue
        who = _identity(c)
        for f in c.get("files") or []:
            if _is_generated(f) or _is_test_path(f):
                continue
            freq[f] = freq.get(f, 0) + 1
            authors.setdefault(f, set()).add(who)
    ranked = sorted(freq.items(), key=lambda kv: -kv[1])[:15]
    return _result(
        "T12",
        status=None,
        summary=f"Top churn paths in {HOTSPOT_WINDOW_DAYS}d (frequency × few authors as a hotspot hint).",
        observations={"hotspots": [
            {"path": p, "changes": n, "authors": len(authors.get(p, set()))} for p, n in ranked
        ]},
        evidence={"paths": [p for p, _ in ranked]},
        evidence_flags={"observed": True},
    )


def check_t13(ctx: RepoContext) -> dict:
    return _unknown(
        "T13",
        "UNSUPPORTED_ADAPTER",
        "Pipeline reliability needs job/pipeline history with first-attempt vs eventual success.",
        missing=["gitlab_api"],
    )


def check_t14(ctx: RepoContext) -> dict:
    return _unknown(
        "T14",
        "UNSUPPORTED_ADAPTER",
        "DORA metrics need production deployments and incident/remediation events. Git log is not a substitute. Missing series stay UNKNOWN separately.",
        missing=["deployments", "incidents"],
        remediation="Wire deploy events (service, env, digest, commit) and incident linkage before scoring DORA.",
    )


RUNNERS = {
    "R01": check_r01, "R02": check_r02, "R03": check_r03, "R04": check_r04,
    "R05": check_r05, "R06": check_r06, "R07": check_r07, "R08": check_r08,
    "D01": check_d01, "D02": check_d02, "D03": check_d03, "D04": check_d04,
    "D05": check_d05, "D06": check_d06, "D07": check_d07, "D08": check_d08,
    "D09": check_d09, "D10": check_d10,
    "G01": check_g01, "G02": check_g02, "G03": check_g03, "G04": check_g04,
    "G05": check_g05, "G06": check_g06, "G07": check_g07, "G08": check_g08,
    "G09": check_g09, "G10": check_g10, "G11": check_g11, "G12": check_g12,
    "Q01": check_q01, "Q02": check_q02, "Q03": check_q03, "Q04": check_q04,
    "Q05": check_q05, "Q06": check_q06, "Q07": check_q07, "Q08": check_q08,
    "Q09": check_q09, "Q10": check_q10,
    "S01": check_s01, "S02": check_s02, "S03": check_s03, "S04": check_s04,
    "S05": check_s05, "S06": check_s06, "S07": check_s07, "S08": check_s08,
    "S09": check_s09, "S10": check_s10, "S11": check_s11, "S12": check_s12,
    "L01": check_l01, "L02": check_l02, "L03": check_l03, "L04": check_l04,
    "L05": check_l05, "L06": check_l06,
    "T01": check_t01, "T02": check_t02, "T03": check_t03, "T04": check_t04,
    "T05": check_t05, "T06": check_t06, "T07": check_t07, "T08": check_t08,
    "T09": check_t09, "T10": check_t10, "T11": check_t11, "T12": check_t12,
    "T13": check_t13, "T14": check_t14,
}


def run_all(ctx: RepoContext, on_each=None) -> list[dict]:
    results: list[dict] = []
    total = len(CHECKS)
    for i, spec in enumerate(CHECKS, start=1):
        fn = RUNNERS[spec["id"]]
        try:
            item = fn(ctx)
        except Exception as exc:
            item = _unknown(
                spec["id"],
                "CHECK_ERROR",
                f"Check raised {type(exc).__name__}: {exc}",
            )
        results.append(item)
        if on_each:
            on_each(results, spec["id"], i, total)
    return results
