"""LT01–LT16 linting checks from docs/repository-checks/linting.md.

Static file and CI-config analysis only. Config files that execute code
(ESLint JS/TS, R .lintr, Gradle) are not evaluated by running them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from gitscore_back.checks import (
    RepoContext,
    _ci_paths,
    _codeowners_match,
    _codeowners_path,
    _config_present,
    _is_binary_path,
    _is_generated,
    _parse_codeowners,
    _read_text,
    _result,
    _unknown,
)

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

PRIMARY_EXTS: dict[str, tuple[str, ...]] = {
    "python": (".py", ".pyi"),
    "js_ts": (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"),
    "java": (".java",),
    "csharp": (".cs",),
    "c_cpp": (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"),
    "go": (".go",),
    "rust": (".rs",),
    "php": (".php",),
    "ruby": (".rb",),
    "kotlin": (".kt", ".kts"),
    "swift": (".swift",),
    "dart": (".dart",),
    "scala": (".scala", ".sc"),
    "r": (".r",),
}

AUX_EXTS: dict[str, tuple[str, ...]] = {
    "shell": (".sh", ".bash", ".ksh", ".zsh"),
    "sql": (".sql",),
    "css": (".css", ".scss", ".sass", ".less"),
    "yaml": (".yml", ".yaml"),
    "markdown": (".md", ".mdx"),
    "terraform": (".tf", ".tfvars"),
}

# name, role, languages, exact files, path substrings, manifest/CI tokens
TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "ruff", "role": "lint", "langs": ["python"], "files": ("ruff.toml", ".ruff.toml"), "substr": (), "tokens": ("ruff check", "ruff"), "sections": ("tool.ruff",)},
    {"name": "ruff-format", "role": "format", "langs": ["python"], "files": ("ruff.toml", ".ruff.toml"), "substr": (), "tokens": ("ruff format", "ruff-format"), "sections": ("tool.ruff.format", "tool.ruff")},
    {"name": "pylint", "role": "lint", "langs": ["python"], "files": (".pylintrc", "pylintrc"), "substr": (), "tokens": ("pylint",), "sections": ("tool.pylint",)},
    {"name": "flake8", "role": "lint", "langs": ["python"], "files": (".flake8",), "substr": (), "tokens": ("flake8",), "sections": ("flake8", "tool.flake8")},
    {"name": "black", "role": "format", "langs": ["python"], "files": (), "substr": (), "tokens": ("black",), "sections": ("tool.black",)},
    {"name": "eslint", "role": "lint", "langs": ["js_ts"], "files": (), "substr": ("eslint.config", ".eslintrc"), "tokens": ("eslint",), "sections": ()},
    {"name": "biome", "role": "lint", "langs": ["js_ts"], "files": ("biome.json", "biome.jsonc"), "substr": (), "tokens": ("biome lint", "biome check", "biome"), "sections": ()},
    {"name": "prettier", "role": "format", "langs": ["js_ts"], "files": (".prettierrc", ".prettierrc.json", ".prettierrc.yml", ".prettierrc.yaml", ".prettierrc.js", "prettier.config.js", "prettier.config.cjs", "prettier.config.mjs"), "substr": ("prettier.config", "/.prettierrc"), "tokens": ("prettier",), "sections": ()},
    {"name": "checkstyle", "role": "lint", "langs": ["java"], "files": ("checkstyle.xml",), "substr": ("checkstyle",), "tokens": ("checkstyle",), "sections": ()},
    {"name": "pmd", "role": "lint", "langs": ["java"], "files": ("pmd.xml",), "substr": ("/pmd", "pmd-rules"), "tokens": ("pmd",), "sections": ()},
    {"name": "spotbugs", "role": "static-analysis", "langs": ["java"], "files": (), "substr": ("spotbugs",), "tokens": ("spotbugs",), "sections": ()},
    {"name": "roslyn", "role": "lint", "langs": ["csharp"], "files": (".globalconfig", "directory.build.props", "directory.build.targets"), "substr": (".csproj",), "tokens": ("enableNETAnalyzers", "analysislevel", "dotnet format", "treatwarningsaserrors"), "sections": ()},
    {"name": "clang-tidy", "role": "lint", "langs": ["c_cpp"], "files": (".clang-tidy",), "substr": (), "tokens": ("clang-tidy",), "sections": ()},
    {"name": "cppcheck", "role": "static-analysis", "langs": ["c_cpp"], "files": (), "substr": ("cppcheck",), "tokens": ("cppcheck",), "sections": ()},
    {"name": "clang-format", "role": "format", "langs": ["c_cpp"], "files": (".clang-format",), "substr": (), "tokens": ("clang-format",), "sections": ()},
    {"name": "golangci-lint", "role": "lint", "langs": ["go"], "files": (".golangci.yml", ".golangci.yaml", ".golangci.toml", ".golangci.json"), "substr": (".golangci.",), "tokens": ("golangci-lint", "golangci"), "sections": ()},
    {"name": "staticcheck", "role": "static-analysis", "langs": ["go"], "files": ("staticcheck.conf",), "substr": (), "tokens": ("staticcheck",), "sections": ()},
    {"name": "gofmt", "role": "format", "langs": ["go"], "files": (), "substr": (), "tokens": ("gofmt", "gofumpt", "go fmt"), "sections": ()},
    {"name": "clippy", "role": "lint", "langs": ["rust"], "files": ("clippy.toml", ".clippy.toml"), "substr": (), "tokens": ("cargo clippy", "clippy"), "sections": ("lints", "workspace.lints")},
    {"name": "rustfmt", "role": "format", "langs": ["rust"], "files": ("rustfmt.toml",), "substr": (), "tokens": ("cargo fmt", "rustfmt"), "sections": ()},
    {"name": "phpcs", "role": "lint", "langs": ["php"], "files": ("phpcs.xml", ".phpcs.xml", "phpcs.xml.dist", ".phpcs.xml.dist"), "substr": ("phpcs.xml",), "tokens": ("phpcs", "php_codesniffer"), "sections": ()},
    {"name": "phpstan", "role": "static-analysis", "langs": ["php"], "files": ("phpstan.neon", "phpstan.neon.dist"), "substr": ("phpstan",), "tokens": ("phpstan",), "sections": ()},
    {"name": "rubocop", "role": "lint", "langs": ["ruby"], "files": (".rubocop.yml", ".rubocop.yaml"), "substr": (".rubocop.",), "tokens": ("rubocop",), "sections": ()},
    {"name": "detekt", "role": "lint", "langs": ["kotlin"], "files": ("detekt.yml", "detekt.yaml"), "substr": ("detekt",), "tokens": ("detekt",), "sections": ()},
    {"name": "ktlint", "role": "format", "langs": ["kotlin"], "files": (), "substr": (), "tokens": ("ktlint",), "sections": ()},
    {"name": "swiftlint", "role": "lint", "langs": ["swift"], "files": (".swiftlint.yml", ".swiftlint.yaml"), "substr": ("swiftlint",), "tokens": ("swiftlint",), "sections": ()},
    {"name": "dart-analyzer", "role": "lint", "langs": ["dart"], "files": ("analysis_options.yaml",), "substr": (), "tokens": ("dart analyze", "flutter analyze"), "sections": ()},
    {"name": "scalafix", "role": "lint", "langs": ["scala"], "files": (".scalafix.conf",), "substr": ("scalafix",), "tokens": ("scalafix",), "sections": ()},
    {"name": "scalafmt", "role": "format", "langs": ["scala"], "files": (".scalafmt.conf",), "substr": (), "tokens": ("scalafmt",), "sections": ()},
    {"name": "lintr", "role": "lint", "langs": ["r"], "files": (".lintr",), "substr": (), "tokens": ("lintr",), "sections": ()},
    {"name": "shellcheck", "role": "lint", "langs": ["shell"], "files": (".shellcheckrc", "shellcheckrc"), "substr": (), "tokens": ("shellcheck",), "sections": ()},
    {"name": "sqlfluff", "role": "lint", "langs": ["sql"], "files": (".sqlfluff",), "substr": (), "tokens": ("sqlfluff",), "sections": ("tool.sqlfluff",)},
    {"name": "stylelint", "role": "lint", "langs": ["css"], "files": (), "substr": ("stylelint.config", ".stylelintrc"), "tokens": ("stylelint",), "sections": ()},
    {"name": "yamllint", "role": "lint", "langs": ["yaml"], "files": (".yamllint", ".yamllint.yaml", ".yamllint.yml"), "substr": ("yamllint",), "tokens": ("yamllint",), "sections": ()},
    {"name": "hadolint", "role": "lint", "langs": ["dockerfile"], "files": (".hadolint.yaml", ".hadolint.yml", "hadolint.yaml"), "substr": ("hadolint",), "tokens": ("hadolint",), "sections": ()},
    {"name": "tflint", "role": "lint", "langs": ["terraform"], "files": (".tflint.hcl",), "substr": ("tflint",), "tokens": ("tflint",), "sections": ()},
    {"name": "markdownlint", "role": "lint", "langs": ["markdown"], "files": (".markdownlint.json", ".markdownlint.yaml", ".markdownlint.yml", ".markdownlintrc", ".markdownlint-cli2.jsonc"), "substr": ("markdownlint",), "tokens": ("markdownlint",), "sections": ()},
]

LINT_TOKENS = (
    "ruff", "eslint", "biome", "pylint", "flake8", "golangci", "clippy", "rubocop",
    "phpcs", "phpstan", "detekt", "ktlint", "swiftlint", "shellcheck", "hadolint",
    "sqlfluff", "stylelint", "yamllint", "tflint", "markdownlint", "checkstyle",
    "clang-tidy", "cppcheck", "scalafix", "lintr", "pre-commit", "lint-staged",
    "npm run lint", "pnpm lint", "yarn lint", "make lint", "cargo clippy",
    "dart analyze", "flutter analyze", "dotnet format",
)
FORMAT_TOKENS = (
    "prettier", "ruff format", "ruff-format", "black", "gofmt", "gofumpt",
    "rustfmt", "clang-format", "scalafmt", "ktlint", "biome format", "biome check",
    "--check", "format check", "verify-no-changes",
)
BYPASS_RE = re.compile(
    r"allow_failure\s*:\s*true|continue-on-error\s*:\s*true|\|\|\s*true",
    re.I,
)
SUPPRESS_RE = re.compile(
    r"(eslint-disable(?:-next-line)?|ruff:\s*noqa|noqa:\s*\*|pylint:\s*disable=all|"
    r"nolint|golangci-lint-disable|swiftlint:disable|hadolint ignore)",
    re.I,
)
BLANKET_IGNORE_RE = re.compile(
    r"(?m)^(\*|/\*\*|/\*\*/?|\*\*/?)\s*$|ignore\s*=\s*\[?\s*[\"']\*[\"']",
)
HOOK_ID_RE = re.compile(r"^\s+(?:id|alias):\s*['\"]?([A-Za-z0-9_.-]+)", re.M)
SCRIPT_LINT_RE = re.compile(r"^(lint|format|check|typecheck)(:|$)", re.I)
MAKE_LINT_RE = re.compile(r"^(lint|format|check)[^\n:]*:", re.M)
PIN_REV_RE = re.compile(r"^\s+rev:\s*(\S+)", re.M)
REPORT_TOKENS = (
    "sarif", "codequality", "code-quality", "gl-code-quality", "eslint-formatter",
    "ruff --output-format", "output-format json", "junit", "--format json",
    "checkstyle", "sonar",
)
EXECUTABLE_CONFIG_SUFFIXES = {".js", ".cjs", ".mjs", ".ts", ".mts", ".cts", ".py"}
OVERVIEW_IDS = ("LT01", "LT02", "LT05", "LT09", "LT10", "LT11")
PRIMARY_MIN_FILES = 3


def _as_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _find_tool_files(ctx: RepoContext, names: tuple[str, ...] | str, substr: tuple[str, ...] | str = ()) -> list[str]:
    names_t = _as_tuple(names)
    substr_t = tuple(s for s in _as_tuple(substr) if len(s) >= 4)
    name_set = {n.lower() for n in names_t}
    hits: list[str] = []
    for path in ctx.tracked:
        low = path.replace("\\", "/").lower()
        base = Path(low).name
        if base in name_set or low in name_set:
            hits.append(path)
            continue
        if any(s.lower() in low for s in substr_t):
            hits.append(path)
    for name in names_t:
        if (ctx.path / name).is_file():
            rel = name.replace("\\", "/")
            if rel not in hits:
                hits.append(rel)
    return _unique(hits)


def _basename(path: str) -> str:
    return Path(path.replace("\\", "/")).name.lower()


def _is_dockerfile(path: str) -> bool:
    name = _basename(path)
    return name.startswith("dockerfile") or name.endswith(".dockerfile")


def _lang_files(ctx: RepoContext, exts: tuple[str, ...]) -> list[str]:
    low_exts = tuple(e.lower() for e in exts)
    out = []
    for path in ctx.tracked:
        if _is_generated(path):
            continue
        if path.lower().endswith(low_exts):
            out.append(path)
    return out


def _shell_files(ctx: RepoContext) -> list[str]:
    files = _lang_files(ctx, AUX_EXTS["shell"])
    for path in ctx.tracked:
        if _is_generated(path):
            continue
        if _basename(path) in {"makefile"}:
            continue
        if path in files:
            continue
        if not Path(path).suffix and not _is_binary_path(path):
            text = _read_text(ctx, path, 400)
            if text.startswith("#!/") and re.search(r"\b(bash|sh|zsh|ksh)\b", text.split("\n", 1)[0]):
                files.append(path)
    return files


def _docker_files(ctx: RepoContext) -> list[str]:
    return [p for p in ctx.tracked if (not _is_generated(p)) and _is_dockerfile(p)]


def _load_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _load_toml(text: str) -> Any | None:
    if not tomllib:
        return None
    try:
        return tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return None


def _section_present(blob: str, section: str) -> bool:
    dotted = section.replace(".", r"\.")
    return re.search(rf"\[{dotted}\]|\[{dotted}\.", blob, re.I) is not None


def _package_json(ctx: RepoContext) -> dict:
    raw = _read_text(ctx, "package.json", 120_000)
    data = _load_json(raw) if raw else None
    return data if isinstance(data, dict) else {}


def _pyproject_text(ctx: RepoContext) -> str:
    return _read_text(ctx, "pyproject.toml", 120_000)


def _cargo_text(ctx: RepoContext) -> str:
    hits = [p for p in ctx.tracked if _basename(p) == "cargo.toml"]
    if not hits:
        return ""
    return _read_text(ctx, hits[0], 80_000)


def _blob_mentions(blob: str, tokens: tuple[str, ...] | list[str]) -> list[str]:
    low = blob.lower()
    return [t for t in tokens if t.lower() in low]


def _lint_profile(ctx: RepoContext) -> dict[str, Any]:
    cached = ctx.__dict__.get("_lint_profile_cache")
    if cached is not None:
        return cached
    profile = _build_lint_profile(ctx)
    ctx.__dict__["_lint_profile_cache"] = profile
    return profile


def _build_lint_profile(ctx: RepoContext) -> dict[str, Any]:
    languages: dict[str, dict[str, Any]] = {}
    for lang, exts in PRIMARY_EXTS.items():
        files = _lang_files(ctx, exts)
        if lang == "r":
            files = [p for p in files if p.lower().endswith(".r")]
        languages[lang] = {"kind": "primary", "files": files, "count": len(files), "tools": []}
    languages["shell"] = {"kind": "aux", "files": _shell_files(ctx), "count": 0, "tools": []}
    languages["shell"]["count"] = len(languages["shell"]["files"])
    for lang, exts in AUX_EXTS.items():
        if lang == "shell":
            continue
        files = _lang_files(ctx, exts)
        languages[lang] = {"kind": "aux", "files": files, "count": len(files), "tools": []}
    docker = _docker_files(ctx)
    languages["dockerfile"] = {"kind": "aux", "files": docker, "count": len(docker), "tools": []}

    ci_paths = _ci_paths(ctx)
    precommit = _config_present(ctx, (".pre-commit-config.yaml", ".pre-commit-config.yml"))
    husky = [p for p in ctx.tracked if p.replace("\\", "/").startswith(".husky/") and not p.endswith("/")]
    lefthook = _config_present(ctx, ("lefthook.yml", "lefthook.yaml", ".lefthook.yml", ".lefthook.yaml"))
    lintstaged = _config_present(
        ctx,
        (".lintstagedrc", ".lintstagedrc.json", ".lintstagedrc.yaml", ".lintstagedrc.yml", "lint-staged.config.js", "lint-staged.config.mjs", "lint-staged.config.cjs"),
        ("lint-staged.config", ".lintstagedrc"),
    )
    pkg = _package_json(ctx)
    if isinstance(pkg.get("lint-staged"), dict):
        lintstaged = _unique(["package.json"] + lintstaged)

    pyproject = _pyproject_text(ctx)
    cargo = _cargo_text(ctx)
    hook_text = "\n".join(_read_text(ctx, p, 80_000) for p in precommit[:2] + husky[:6] + lefthook[:2])
    ci_text = "\n".join(_read_text(ctx, p, 80_000) for p in ci_paths[:10])
    pkg_blob = json.dumps(pkg).lower() if pkg else ""
    scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
    script_blob = " ".join(f"{k} {v}" for k, v in scripts.items())
    deps = {}
    for key in ("dependencies", "devDependencies", "optionalDependencies"):
        if isinstance(pkg.get(key), dict):
            deps.update(pkg[key])
    dep_names = {str(k).lower() for k in deps}

    search_blob = "\n".join([ci_text, hook_text, pkg_blob, script_blob, pyproject, cargo]).lower()

    tools: list[dict[str, Any]] = []
    for spec in TOOL_SPECS:
        files = _find_tool_files(ctx, spec["files"], spec.get("substr") or ())
        section_hits = [s for s in spec.get("sections") or () if _section_present(pyproject, s) or _section_present(cargo, s)]
        if section_hits and pyproject:
            files.append("pyproject.toml")
        if any(s in ("lints", "workspace.lints") for s in section_hits) and cargo:
            files.append(next((p for p in ctx.tracked if _basename(p) == "cargo.toml"), "Cargo.toml"))
        token_hits = _blob_mentions(search_blob, spec["tokens"])
        in_deps = spec["name"] in dep_names or any(spec["name"] in d for d in dep_names)
        if spec["name"] == "eslint" and any(d in dep_names for d in ("eslint", "@eslint/js", "typescript-eslint")):
            in_deps = True
        if spec["name"] == "ruff" and re.search(r"\bruff\b", pyproject, re.I):
            token_hits = _unique(["ruff"] + token_hits)
        declared = bool(files or section_hits or token_hits or in_deps)
        if not declared:
            continue
        mode = "file" if files or section_hits else ("shared" if in_deps else "defaults")
        tool = {
            "name": spec["name"],
            "role": spec["role"],
            "langs": list(spec["langs"]),
            "config_paths": _unique(files),
            "configuration_mode": mode,
            "tokens": token_hits,
            "in_dependencies": in_deps,
        }
        tools.append(tool)
        for lang in spec["langs"]:
            if lang in languages:
                languages[lang]["tools"].append(spec["name"])

    for path in _config_present(ctx, ("setup.cfg", "tox.ini")):
        if re.search(r"\[flake8\]", _read_text(ctx, path, 40_000), re.I):
            if not any(t["name"] == "flake8" for t in tools):
                tools.append({"name": "flake8", "role": "lint", "langs": ["python"], "config_paths": [path], "configuration_mode": "file", "tokens": ["flake8"], "in_dependencies": False})
            languages["python"]["tools"] = _unique(languages["python"]["tools"] + ["flake8"])

    # Clippy may have no extra file when Cargo.toml / CI invokes it.
    if languages["rust"]["count"] and not languages["rust"]["tools"]:
        if "clippy" in search_blob or "[lints]" in cargo.lower() or "rust-toolchain" in " ".join(ctx.tracked).lower():
            tools.append({"name": "clippy", "role": "lint", "langs": ["rust"], "config_paths": [], "configuration_mode": "defaults", "tokens": ["clippy"], "in_dependencies": False})
            languages["rust"]["tools"].append("clippy")

    hook_ids = HOOK_ID_RE.findall(hook_text)
    lint_scripts = sorted(k for k in scripts if SCRIPT_LINT_RE.search(str(k)) or "lint" in str(k).lower())
    make_paths = [p for p in ctx.tracked if _basename(p) in {"makefile", "gnumakefile"}]
    make_text = "\n".join(_read_text(ctx, p, 40_000) for p in make_paths[:2])
    make_targets = MAKE_LINT_RE.findall(make_text)
    just_paths = _config_present(ctx, ("justfile", "Justfile"))
    tox = _config_present(ctx, ("tox.ini",))
    documented = []
    for label, present in (
        ("package.json scripts", lint_scripts),
        ("Makefile", make_targets),
        ("justfile", just_paths),
        ("tox.ini", tox and "lint" in _read_text(ctx, tox[0], 20_000).lower()),
        ("pre-commit", precommit),
    ):
        if present:
            documented.append(label)

    readme_hits = []
    for p in ctx.tracked:
        if _basename(p).startswith("readme") and p.lower().endswith((".md", ".rst", ".txt")):
            text = _read_text(ctx, p, 40_000).lower()
            if re.search(r"\b(make lint|npm run lint|pnpm lint|yarn lint|ruff check|pre-commit run)\b", text):
                readme_hits.append(p)
                documented.append(p)
            break

    lockfiles = [
        p for p in ctx.tracked
        if _basename(p) in {
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb",
            "uv.lock", "poetry.lock", "pipfile.lock", "cargo.lock", "composer.lock",
            "gemfile.lock", "go.sum", "pubspec.lock",
        }
    ]
    pins = []
    for p in precommit[:2]:
        if PIN_REV_RE.search(_read_text(ctx, p, 80_000)):
            pins.append(p)
    if any(_basename(p) == "rust-toolchain.toml" or _basename(p) == "rust-toolchain" for p in ctx.tracked):
        pins.append("rust-toolchain")
    if any(_basename(p) == "go.mod" for p in ctx.tracked):
        pins.append("go.mod")

    ignore_files = _config_present(
        ctx,
        (".eslintignore", ".prettierignore", ".ruffignore", ".markdownlintignore"),
        ("eslintignore", "prettierignore", "per-file-ignores"),
    )
    baseline_files = [
        p for p in ctx.tracked
        if any(x in _basename(p) for x in ("baseline", "rubocop_todo", ".lint-todo"))
    ]

    ci_lint_tokens = _blob_mentions(ci_text, LINT_TOKENS)
    format_in_ci = bool(_blob_mentions(ci_text.lower(), FORMAT_TOKENS))
    lint_jobs = _lint_jobs(ci_text)
    bypassed_jobs = [j["name"] for j in lint_jobs if j.get("bypassed")]
    reports = _blob_mentions(ci_text + "\n" + hook_text, REPORT_TOKENS)

    profile = {
        "languages": languages,
        "tools": tools,
        "lint_tools": [t for t in tools if t["role"] in {"lint", "static-analysis"}],
        "format_tools": [t for t in tools if t["role"] == "format"],
        "precommit": precommit,
        "husky": husky,
        "lefthook": lefthook,
        "lintstaged": lintstaged,
        "hook_ids": _unique(hook_ids),
        "ci_paths": ci_paths,
        "ci_text": ci_text,
        "ci_lint_tokens": ci_lint_tokens,
        "format_in_ci": format_in_ci,
        "lint_jobs": lint_jobs,
        "bypassed_jobs": bypassed_jobs,
        "scripts": lint_scripts,
        "make_targets": make_targets,
        "documented_commands": _unique(documented),
        "readme_hits": readme_hits,
        "lockfiles": lockfiles,
        "pins": _unique(pins + lockfiles[:8]),
        "ignore_files": ignore_files,
        "baseline_files": baseline_files,
        "reports": reports,
        "package_scripts": scripts,
        "pyproject": pyproject,
        "hook_text": hook_text,
        "search_blob": search_blob,
    }
    return profile


def _lint_jobs(ci_text: str) -> list[dict[str, Any]]:
    if not ci_text.strip():
        return []
    jobs: list[dict[str, Any]] = []
    chunks = re.split(r"\n(?=[A-Za-z0-9_.-]+(?:\s*)?:)", ci_text)
    for chunk in chunks:
        low = chunk.lower()
        if not any(tok in low for tok in LINT_TOKENS):
            continue
        first = chunk.split(":", 1)[0].strip().strip("- ").strip("'\"")
        name = first[:80] or "lint"
        jobs.append({"name": name, "bypassed": bool(BYPASS_RE.search(chunk)), "sample": chunk[:240]})
    if not jobs and any(tok in ci_text.lower() for tok in LINT_TOKENS):
        jobs.append({"name": "(ci)", "bypassed": bool(BYPASS_RE.search(ci_text)), "sample": ci_text[:240]})
    return jobs


def _present_langs(profile: dict, *, kind: str | None = None, min_files: int = 1) -> list[str]:
    out = []
    for name, info in profile["languages"].items():
        if kind and info["kind"] != kind:
            continue
        if info["count"] >= min_files:
            out.append(name)
    return out


def _primary_langs(profile: dict) -> list[str]:
    present = _present_langs(profile, kind="primary", min_files=1)
    if not present:
        return []
    strong = [n for n in present if profile["languages"][n]["count"] >= PRIMARY_MIN_FILES]
    return strong or present


def _covered(profile: dict, lang: str) -> bool:
    return bool(profile["languages"].get(lang, {}).get("tools"))


def _tool_paths(profile: dict) -> list[str]:
    paths: list[str] = []
    for tool in profile["tools"]:
        paths.extend(tool.get("config_paths") or [])
    paths.extend(profile["precommit"])
    paths.extend(profile["ci_paths"][:5])
    return _unique(paths)


def _na(check_id: str, summary: str) -> dict:
    return _result(check_id, status="NOT_APPLICABLE", summary=summary, reason_code="NOT_APPLICABLE", evidence={"paths": []})


def check_lt01(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    primary = _primary_langs(profile)
    aux = [n for n in _present_langs(profile, kind="aux", min_files=3)]
    if not primary and not _present_langs(profile, min_files=1):
        return _na("LT01", "No authored source languages detected for linter coverage.")
    missing_primary = [n for n in primary if not _covered(profile, n)]
    missing_aux = [n for n in aux if not _covered(profile, n)]
    covered = [n for n in primary + aux if _covered(profile, n)]
    if missing_primary:
        status = "FAIL"
        summary = f"No suitable linter for primary language(s): {', '.join(missing_primary)}."
        rem = "Add a language-appropriate linter (see docs/repository-checks/linting.md) and bind it to the source scope."
    elif missing_aux:
        status = "WARN"
        summary = f"Primary languages are covered; extra file types without a linter: {', '.join(missing_aux)}."
        rem = "Add ShellCheck, Hadolint, SQLFluff, yamllint or an equivalent for auxiliary files, or record an exclusion."
    else:
        status = "PASS"
        summary = f"Linter coverage found for {', '.join(covered) or 'detected languages'}."
        rem = None
    return _result(
        "LT01",
        status=status,
        summary=summary,
        observations={"primary": primary, "aux": aux, "missing_primary": missing_primary, "missing_aux": missing_aux, "tools": [t["name"] for t in profile["lint_tools"]]},
        evidence={"paths": _tool_paths(profile)[:20]},
        evidence_flags={"declared": bool(covered)},
        remediation=rem,
    )


def check_lt02(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    if not _primary_langs(profile) and not profile["lint_tools"]:
        return _na("LT02", "No languages or linters to declare configuration for.")
    lint_tools = profile["lint_tools"]
    if not lint_tools:
        return _result(
            "LT02",
            status="FAIL",
            summary="A linter is required for the detected languages, but no effective config, pinned defaults, or tool invocation was found.",
            evidence={"paths": []},
            observations={"configuration_mode": None},
            evidence_flags={"declared": False},
            remediation="Commit a tool config, a pinned shared preset, or document the pinned CLI defaults.",
        )
    modes = {t["configuration_mode"] for t in lint_tools}
    files = [p for t in lint_tools for p in t["config_paths"]]
    if "file" in modes or "shared" in modes:
        status = "PASS"
        mode = "file" if "file" in modes else "shared"
        summary = f"Effective lint configuration declared ({mode}: {(files or [lint_tools[0]['name']])[0]})."
        rem = None
    else:
        status = "PASS"
        mode = "defaults"
        summary = f"No extra config file; pinned/default policy inferred from {lint_tools[0]['name']} invocation."
        rem = "Record the accepted default profile and tool version so rule changes are not silent."
    return _result(
        "LT02",
        status=status,
        summary=summary,
        observations={"configuration_mode": mode, "tools": [t["name"] for t in lint_tools]},
        evidence={"paths": _unique(files + profile["precommit"])[:15]},
        evidence_flags={"declared": True},
        remediation=rem,
    )


def _classify_config(path: str, text: str) -> str:
    if not text.strip():
        return "empty"
    suffix = Path(path).suffix.lower()
    name = _basename(path)
    if suffix in EXECUTABLE_CONFIG_SUFFIXES or name in {".lintr"}:
        return "executable"
    if suffix == ".json" or name.endswith(".jsonc"):
        # jsonc: strip comments roughly
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        stripped = re.sub(r"^\s*//.*$", "", stripped, flags=re.M)
        return "ok" if _load_json(stripped) is not None else "invalid"
    if suffix == ".toml":
        if tomllib is None:
            return "unknown"
        return "ok" if _load_toml(text) is not None else "invalid"
    if suffix in {".yml", ".yaml", ".neon"} or name.endswith((".yml", ".yaml")):
        return "ok"
    return "unknown"


def check_lt03(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    paths = _unique([p for t in profile["tools"] for p in t["config_paths"] if p] + profile["precommit"])
    if not paths:
        if profile["lint_tools"]:
            return _result(
                "LT03",
                status="PASS",
                summary="No extra config file to resolve; tool defaults/CLI flags are in use.",
                observations={"configuration_mode": "defaults"},
                evidence={"paths": []},
                evidence_flags={"declared": True},
            )
        return _na("LT03", "No linter configuration to resolve.")
    classes: dict[str, str] = {}
    for path in paths[:20]:
        classes[path] = _classify_config(path, _read_text(ctx, path, 80_000))
    invalid = [p for p, c in classes.items() if c == "invalid"]
    empty = [p for p, c in classes.items() if c == "empty"]
    executable = [p for p, c in classes.items() if c == "executable"]
    if invalid:
        return _result(
            "LT03",
            status="FAIL",
            summary=f"Lint config does not parse: {invalid[0]}.",
            observations={"config_status": classes},
            evidence={"paths": invalid + empty},
            evidence_flags={"declared": True, "configured": False},
            remediation="Fix the invalid config (JSON/TOML) so the installed tool version can load it.",
        )
    if empty:
        return _result(
            "LT03",
            status="FAIL",
            summary=f"Lint config is empty: {empty[0]}.",
            observations={"config_status": classes},
            evidence={"paths": empty},
            evidence_flags={"declared": True, "configured": False},
            remediation="Put a resolvable policy in the config or remove the unused file.",
        )
    if executable and not any(c == "ok" for c in classes.values()):
        return _unknown(
            "LT03",
            "UNSAFE_TO_EXECUTE",
            "Config is executable (JS/TS/R). Static reading does not prove it resolves; the auditor does not execute it.",
            missing=["isolated_tool_run"],
            remediation="Resolve the config with the tool in an isolated runner, or add a data-only config format.",
        )
    return _result(
        "LT03",
        status="PASS",
        summary="Readable lint configs parsed or look well-formed. Plugin/runtime resolution was not executed.",
        observations={"config_status": classes},
        evidence={"paths": list(classes)[:15]},
        evidence_flags={"declared": True, "configured": True, "enforced": None},
        data_quality={"complete": not executable, "missing_sources": ["isolated_tool_run"] if executable else []},
    )


def check_lt04(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    if not profile["lint_tools"]:
        return _na("LT04", "No linter whose rules can be inspected.")
    blobs = []
    paths = []
    for path in _unique([p for t in profile["lint_tools"] for p in t["config_paths"]] + profile["precommit"])[:12]:
        blobs.append(_read_text(ctx, path, 80_000))
        paths.append(path)
    blob = "\n".join(blobs) + "\n" + profile.get("pyproject", "")
    low = blob.lower()
    disabled = bool(re.search(r"select\s*=\s*\[\s*\]|ignore\s*=\s*\[?\s*[\"']all[\"']|rules\s*:\s*\{\s*\}", low))
    has_preset = bool(re.search(r"extends|preset|include:|select\s*=|linter\.rules|recommended|strict", low))
    if disabled:
        return _result(
            "LT04",
            status="FAIL",
            summary="Lint rules look globally emptied or ignored (empty select/rules or ignore ALL).",
            evidence={"paths": paths[:12]},
            evidence_flags={"declared": True},
            remediation="Enable a coherent baseline; do not disable required rules for all production code.",
        )
    if has_preset or any(t["configuration_mode"] == "defaults" for t in profile["lint_tools"]):
        return _result(
            "LT04",
            status="PASS",
            summary="A rule preset, select list, or documented tool defaults is present. Rule IDs were not compared across tools.",
            evidence={"paths": paths[:12]},
            evidence_flags={"declared": True},
        )
    return _result(
        "LT04",
        status="WARN",
        summary="Linter config exists, but no preset/select/extends was found, so the baseline is unclear.",
        evidence={"paths": paths[:12]},
        evidence_flags={"declared": True},
        remediation="Set an explicit recommended/strict preset or select list for the normative rules.",
    )


def check_lt05(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    primary = _primary_langs(profile)
    if not primary:
        return _na("LT05", "No source scope that a linter should cover.")
    if not profile["lint_tools"] and not profile["precommit"]:
        return _result(
            "LT05",
            status="FAIL",
            summary="Required source exists, but no linter selection is configured (0 files can be checked).",
            observations={"primary": primary},
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Point the linter at the authored source/tests/scripts; a silent empty run is not a PASS.",
        )
    blanket = []
    ignored_src = []
    needles = ("src/", "lib/", "app/", "gitscore_")
    for path in profile["ignore_files"][:10]:
        text = _read_text(ctx, path, 40_000)
        if BLANKET_IGNORE_RE.search(text) or re.search(r"(?m)^/\s*$", text):
            blanket.append(path)
        low = text.lower()
        if any(n in low for n in needles) and re.search(r"^(src|lib|app)(/|\s|$)", low, re.M):
            ignored_src.append(path)
    if blanket:
        return _result(
            "LT05",
            status="FAIL",
            summary=f"Ignore/exclude list covers everything ({blanket[0]}); required scope is not analyzed.",
            evidence={"paths": blanket},
            observations={"primary": primary},
            evidence_flags={"declared": True},
            remediation="Replace global `*` excludes with path-scoped ignores that leave production code in scope.",
        )
    if ignored_src:
        return _result(
            "LT05",
            status="WARN",
            summary=f"Source paths appear excluded from lint ({ignored_src[0]}).",
            evidence={"paths": ignored_src[:8]},
            observations={"primary": primary},
            evidence_flags={"declared": True},
            remediation="Keep authored services in the analyzed set; exclude only generated/vendor paths.",
        )
    counts = {n: profile["languages"][n]["count"] for n in primary}
    return _result(
        "LT05",
        status="PASS",
        summary=f"Linter config exists for detected source ({', '.join(f'{k}={v}' for k, v in counts.items())}). File-list from the tool itself was not available.",
        observations={"primary": primary, "file_counts": counts, "coverage_known": False},
        evidence={"paths": _tool_paths(profile)[:15]},
        evidence_flags={"declared": True, "observed": False},
        data_quality={"complete": False, "missing_sources": ["tool_file_list"]},
    )


def check_lt06(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    if not profile["lint_tools"] and not profile["precommit"]:
        return _na("LT06", "No lint toolchain to pin.")
    if profile["pins"] or profile["lockfiles"]:
        return _result(
            "LT06",
            status="PASS",
            summary=f"Lint/tool versions look pinned via {(profile['pins'] or profile['lockfiles'])[0]}.",
            observations={"pins": profile["pins"][:10]},
            evidence={"paths": (profile["pins"] + profile["lockfiles"])[:15]},
            evidence_flags={"declared": True},
        )
    return _result(
        "LT06",
        status="WARN",
        summary="Linters are present, but no lockfile or pinned rev/toolchain was found.",
        evidence={"paths": _tool_paths(profile)[:10]},
        evidence_flags={"declared": False},
        remediation="Pin linter, plugin, and shared-config versions (lockfile, pre-commit `rev`, rust-toolchain, go.mod).",
    )


def check_lt07(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    if not profile["lint_tools"] and not profile["precommit"] and not profile["documented_commands"]:
        if not _primary_langs(profile):
            return _na("LT07", "No lint command is needed without source/linters.")
    if profile["documented_commands"] or profile["scripts"] or profile["make_targets"]:
        label = (profile["documented_commands"] or profile["scripts"] or profile["make_targets"])[0]
        return _result(
            "LT07",
            status="PASS",
            summary=f"Portable lint command found ({label}).",
            observations={"commands": profile["documented_commands"], "scripts": profile["scripts"]},
            evidence={"paths": _unique(profile["readme_hits"] + profile["precommit"] + (["package.json"] if profile["scripts"] else []) + [p for p in ctx.tracked if _basename(p) == "makefile"][:1])[:10]},
            evidence_flags={"declared": True},
        )
    return _result(
        "LT07",
        status="WARN",
        summary="No portable `lint`/`format` command documented (Makefile, package.json, just/tox, or README).",
        evidence={"paths": []},
        evidence_flags={"declared": False},
        remediation="Add `make lint` / `npm run lint` (check vs fix) with cwd and prerequisites, calling the same normative set as CI.",
    )


def check_lt08(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    hooks = profile["precommit"] + profile["husky"] + profile["lefthook"]
    ci_only = bool(profile["ci_lint_tokens"] or profile["lint_jobs"])
    if not hooks:
        if ci_only:
            return _result(
                "LT08",
                status="PASS",
                summary="No local git hook; CI-only lint is allowed. Local hooks are extra feedback, not the merge gate.",
                observations={"ci_only": True},
                evidence={"paths": profile["ci_paths"][:8]},
                evidence_flags={"declared": False, "enforced": None},
            )
        if not profile["lint_tools"]:
            return _na("LT08", "No linter or hook mechanism in use.")
        return _result(
            "LT08",
            status="WARN",
            summary="Linters exist but no pre-commit/Husky/Lefthook hook was found, and CI lint was not detected.",
            evidence={"paths": _tool_paths(profile)[:8]},
            evidence_flags={"declared": False},
            remediation="Add a supported hook that runs the fast checks, or rely on a documented CI-only profile.",
        )
    hook_blob = profile["hook_text"].lower()
    calls_lint = bool(_blob_mentions(hook_blob, LINT_TOKENS)) or bool(profile["hook_ids"]) or bool(profile["lintstaged"])
    if not calls_lint:
        return _result(
            "LT08",
            status="WARN",
            summary=f"Hook config {hooks[0]} exists, but it does not clearly invoke a linter.",
            evidence={"paths": hooks[:10]},
            evidence_flags={"declared": True, "enforced": None},
            remediation="Point the hook at the same fast linters; Husky without a lint command is not integration.",
        )
    return _result(
        "LT08",
        status="PASS",
        summary=f"Local hook invokes lint ({hooks[0]}). Presence of the file does not prove every developer has it installed.",
        observations={"hook_ids": profile["hook_ids"][:15]},
        evidence={"paths": hooks[:12]},
        evidence_flags={"declared": True, "configured": True, "enforced": None},
    )


def check_lt09(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    if not _primary_langs(profile) and not profile["lint_tools"]:
        return _na("LT09", "No lintable changes in scope.")
    if not profile["ci_paths"]:
        return _result(
            "LT09",
            status="FAIL",
            summary="No CI workflow found, so lint cannot run on merge-request revisions.",
            evidence={"paths": []},
            evidence_flags={"declared": False, "observed": False},
            remediation="Add a CI lint job for applicable languages and for changes to lint config/lockfiles.",
        )
    if profile["lint_jobs"] or profile["ci_lint_tokens"]:
        label = (profile["ci_lint_tokens"] or [profile["lint_jobs"][0]["name"]])[0]
        return _result(
            "LT09",
            status="WARN",
            summary=f"CI mentions lint ({label}), but this clone cannot prove the job ran on the evaluated MR SHA.",
            observations={"jobs": [j["name"] for j in profile["lint_jobs"][:8]], "tokens": profile["ci_lint_tokens"][:8]},
            evidence={"paths": profile["ci_paths"][:8]},
            evidence_flags={"declared": True, "configured": True, "observed": False},
            data_quality={"complete": False, "missing_sources": ["gitlab_api"]},
            remediation="Confirm lint jobs run on the merge-request SHA (and on lint-config/lockfile changes), not only when YAML exists.",
        )
    return _result(
        "LT09",
        status="FAIL",
        summary="CI config exists, but no lint job or command was found.",
        evidence={"paths": profile["ci_paths"][:8]},
        evidence_flags={"declared": False, "observed": False},
        remediation="Add a lint job that runs for applicable MRs; a job named test is not a lint gate.",
    )


def check_lt10(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    if not _primary_langs(profile) and not profile["lint_tools"]:
        return _na("LT10", "No linter result to evaluate.")
    if not profile["lint_tools"] and not profile["ci_lint_tokens"] and not profile["precommit"]:
        return _result(
            "LT10",
            status="FAIL",
            summary="No linter is configured, so the revision cannot have a passing lint result.",
            evidence={"paths": []},
            evidence_flags={"observed": False},
            remediation="Configure and run the normative linter; do not treat a green pipeline without lint as a lint PASS.",
        )
    return _unknown(
        "LT10",
        "UNSUPPORTED_ADAPTER",
        "Lint pass/fail on this revision needs the tool exit code or CI report, not only a pipeline name. Configs are not executed here.",
        missing=["ci_artifacts", "isolated_tool_run"],
        remediation="Keep JSON/SARIF/Code Quality reports for the evaluated SHA and fail on findings above the agreed threshold.",
    )


def check_lt11(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    if not _primary_langs(profile) and not profile["lint_tools"]:
        return _na("LT11", "No lint gate applies.")
    if not profile["ci_paths"] or not (profile["lint_jobs"] or profile["ci_lint_tokens"]):
        return _result(
            "LT11",
            status="FAIL",
            summary="Lint is not a CI job, so a lint failure cannot block merge.",
            evidence={"paths": profile["ci_paths"][:6]},
            evidence_flags={"declared": False, "enforced": False},
            remediation="Make lint a required check on the evaluated revision; local hooks are not a merge gate.",
        )
    if profile["bypassed_jobs"]:
        return _result(
            "LT11",
            status="FAIL",
            summary=f"Lint job looks optional or masked (`allow_failure` / `continue-on-error` / `|| true`): {profile['bypassed_jobs'][0]}.",
            observations={"bypassed": profile["bypassed_jobs"]},
            evidence={"paths": profile["ci_paths"][:8]},
            evidence_flags={"declared": True, "enforced": False},
            remediation="Remove allow_failure/continue-on-error/`|| true` from the normative lint job and require it on the merge revision.",
        )
    return _result(
        "LT11",
        status="WARN",
        summary="Lint job is declared without an obvious bypass. Required-check / merge settings were not read from the server.",
        observations={"jobs": [j["name"] for j in profile["lint_jobs"][:8]]},
        evidence={"paths": profile["ci_paths"][:8]},
        evidence_flags={"declared": True, "configured": True, "enforced": None},
        data_quality={"complete": False, "missing_sources": ["gitlab_api"]},
        remediation="Require the lint job on the MR SHA (GitLab merge checks / required status checks).",
    )


def check_lt12(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    fmt = profile["format_tools"]
    if not fmt and not profile["format_in_ci"]:
        if not _primary_langs(profile):
            return _na("LT12", "No source that would use a formatter.")
        return _result(
            "LT12",
            status="WARN",
            summary="No formatter config or format `--check` command found. Formatter policy is optional, but then formatting is unenforced.",
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="If formatting is in policy, run prettier/ruff format/rustfmt/clang-format in check/diff mode in CI.",
        )
    if profile["format_in_ci"]:
        return _result(
            "LT12",
            status="PASS",
            summary="CI mentions a formatter check/diff mode. Auto-fix without verifying the original tree is not enough.",
            evidence={"paths": _unique([p for t in fmt for p in t["config_paths"]] + profile["ci_paths"])[:12]},
            evidence_flags={"declared": True, "observed": False},
        )
    return _result(
        "LT12",
        status="WARN",
        summary=f"Formatter config {(fmt[0]['config_paths'] or [fmt[0]['name']])[0]} found, but CI has no format `--check`/`--diff`.",
        evidence={"paths": _unique([p for t in fmt for p in t["config_paths"]] + profile["ci_paths"])[:12]},
        evidence_flags={"declared": True, "enforced": None},
        remediation="Run the formatter in check mode so unformatted commits fail; editor format-on-save is not enforcement.",
    )


def check_lt13(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    if not profile["precommit"] and not profile["husky"] and not profile["lefthook"]:
        if profile["ci_lint_tokens"] or profile["lint_jobs"]:
            return _result(
                "LT13",
                status="PASS",
                summary="CI-only lint profile: no local hook to disagree with CI. Document any extra heavy CI checks.",
                evidence={"paths": profile["ci_paths"][:6]},
                evidence_flags={"declared": True},
            )
        return _na("LT13", "No local hook and no CI lint to compare.")
    local_blob = profile["hook_text"].lower()
    ci_blob = profile["ci_text"].lower()
    local_tools = _blob_mentions(local_blob, LINT_TOKENS + FORMAT_TOKENS)
    ci_tools = [t for t in local_tools if t.lower() in ci_blob]
    extra_local = [t for t in local_tools if t not in ci_tools]
    if "pre-commit" in ci_blob or (local_tools and not extra_local):
        return _result(
            "LT13",
            status="PASS",
            summary="Local hook tools are named in CI (or CI runs pre-commit). Staged-only local scope is acceptable.",
            observations={"local_tools": local_tools, "ci_overlap": ci_tools},
            evidence={"paths": (profile["precommit"] + profile["husky"][:3] + profile["ci_paths"][:4])[:12]},
            evidence_flags={"declared": True},
        )
    if extra_local and ci_tools:
        return _result(
            "LT13",
            status="WARN",
            summary=f"Local hooks include {', '.join(extra_local)} not mentioned in CI.",
            observations={"local_tools": local_tools, "ci_overlap": ci_tools},
            evidence={"paths": (profile["precommit"] + profile["ci_paths"][:5])[:12]},
            evidence_flags={"declared": True},
            remediation="Keep local hooks a subset of CI; do not run a different rule set only on developer machines.",
        )
    return _result(
        "LT13",
        status="WARN",
        summary="Local hooks exist, but CI does not mention those tools.",
        observations={"local_tools": local_tools},
        evidence={"paths": (profile["precommit"] + profile["ci_paths"][:5])[:12]},
        evidence_flags={"declared": True},
        remediation="Run `pre-commit run --all-files` or the same linters in CI.",
    )


def check_lt14(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    blanket = []
    for path in profile["ignore_files"][:8]:
        text = _read_text(ctx, path, 40_000)
        if BLANKET_IGNORE_RE.search(text) or re.search(r"(?m)^/\s*$", text):
            blanket.append(path)
    inline: list[str] = []
    scanned = 0
    for path in ctx.tracked:
        if _is_generated(path) or _is_binary_path(path):
            continue
        if Path(path).suffix.lower() not in {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".rb", ".java", ".kt"}:
            continue
        scanned += 1
        if scanned > 250:
            break
        if SUPPRESS_RE.search(_read_text(ctx, path, 20_000)):
            inline.append(path)
            if len(inline) >= 20:
                break
    if blanket:
        return _result(
            "LT14",
            status="FAIL",
            summary=f"Blanket ignore/baseline hides the whole tree ({blanket[0]}).",
            observations={"inline_sampled": len(inline), "files_scanned": scanned, "baselines": profile["baseline_files"][:8]},
            evidence={"paths": blanket + profile["baseline_files"][:4] + inline[:6]},
            evidence_flags={"declared": True},
            remediation="Scope ignores; give wide baselines an owner and review condition. Do not treat every noqa as a failure.",
        )
    if profile["baseline_files"]:
        return _result(
            "LT14",
            status="WARN",
            summary=f"Lint baseline/TODO file present ({profile['baseline_files'][0]}); growth should be visible in review.",
            observations={"inline_sampled": len(inline), "files_scanned": scanned},
            evidence={"paths": profile["baseline_files"][:8] + inline[:8]},
            evidence_flags={"declared": True},
            remediation="Require review when the baseline grows; new suppressions should be in the diff with a reason.",
        )
    if len(inline) >= 12:
        return _result(
            "LT14",
            status="WARN",
            summary=f"Inline suppressions in {len(inline)} sampled files. Individual noqa is fine; volume needs owners.",
            observations={"inline_sampled": len(inline), "files_scanned": scanned},
            evidence={"paths": inline[:15]},
            evidence_flags={"observed": True},
            remediation="Bound eslint-disable/noqa/nolint and require a reason; do not fail on a single justified suppression.",
        )
    return _result(
        "LT14",
        status="PASS",
        summary=(
            f"No blanket ignore; {len(inline)} sampled file(s) have inline suppressions."
            if inline
            else "No blanket ignore files or sampled inline suppressions."
        ),
        observations={"inline_sampled": len(inline), "files_scanned": scanned},
        evidence={"paths": profile["ignore_files"][:8] + inline[:8]},
        evidence_flags={"observed": True},
    )


def check_lt15(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    if not profile["lint_tools"] and not profile["ci_lint_tokens"]:
        return _na("LT15", "No linter that could emit a report.")
    if profile["reports"]:
        return _result(
            "LT15",
            status="PASS",
            summary=f"Machine-readable lint report format mentioned ({profile['reports'][0]}). Reports must still be kept on failure.",
            observations={"formats": profile["reports"]},
            evidence={"paths": profile["ci_paths"][:8]},
            evidence_flags={"declared": True, "observed": False},
        )
    return _result(
        "LT15",
        status="WARN",
        summary="Lint is configured, but no JSON/SARIF/Code Quality report export was found in CI.",
        evidence={"paths": profile["ci_paths"][:8] + _tool_paths(profile)[:6]},
        evidence_flags={"declared": False},
        remediation="Export rule id, message, path/line, severity, revision, and tool version (SARIF or GitLab Code Quality). Empty findings ≠ job skipped.",
    )


def check_lt16(ctx: RepoContext) -> dict:
    profile = _lint_profile(ctx)
    lint_ci = profile["ci_paths"] if (profile["lint_jobs"] or profile["ci_lint_tokens"]) else []
    sensitive = _unique(
        [p for t in profile["tools"] for p in t["config_paths"]]
        + profile["precommit"]
        + profile["lefthook"]
        + lint_ci
        + [p for p in profile["husky"][:8]]
        + profile["ignore_files"]
        + profile["baseline_files"]
    )
    if not sensitive:
        return _na("LT16", "No lint configs, hooks, or CI jobs whose owners to check.")
    owners_path = _codeowners_path(ctx)
    if not owners_path:
        return _result(
            "LT16",
            status="WARN",
            summary="Lint/CI/hook configs exist, but there is no CODEOWNERS file covering them.",
            evidence={"paths": sensitive[:15]},
            evidence_flags={"declared": False},
            remediation="Require review of lint configs, suppressions, wrappers, and CI lint jobs (CODEOWNERS or equivalent).",
        )
    rules = _parse_codeowners(_read_text(ctx, owners_path, 80_000))
    uncovered = []
    for path in sensitive[:40]:
        matched = [r for r in rules if _codeowners_match(r[0], path) and r[1]]
        required = [r for r in matched if not r[2]]
        if not required:
            uncovered.append(path)
    if uncovered:
        return _result(
            "LT16",
            status="WARN",
            summary=f"{len(uncovered)} lint/CI/hook path(s) lack a required CODEOWNER, e.g. {uncovered[0]}.",
            observations={"uncovered": uncovered[:15]},
            evidence={"paths": [owners_path] + uncovered[:12]},
            evidence_flags={"declared": True, "enforced": None},
            remediation="Cover lint configs, baselines, and CI lint jobs with required owners so a MR cannot silently drop the control.",
        )
    return _result(
        "LT16",
        status="PASS",
        summary=f"CODEOWNERS matches sampled lint/CI/hook paths ({owners_path}). Actual MR review still needs approval events.",
        evidence={"paths": [owners_path] + sensitive[:10]},
        evidence_flags={"declared": True, "observed": False},
        data_quality={"complete": False, "missing_sources": ["gitlab_api"]},
    )


def check_q06(ctx: RepoContext) -> dict:
    """Fallback overview; run_all overwrites this from LT results when present."""
    return overview_q06(ctx, {})


def overview_q06(ctx: RepoContext, by_id: dict[str, dict]) -> dict:
    profile = _lint_profile(ctx)
    lt_status = {}
    for cid in OVERVIEW_IDS:
        item = by_id.get(cid) or {}
        lt_status[cid] = item.get("status")
    present = [s for s in lt_status.values() if s is not None]
    known = [s for s in present if s not in {"UNKNOWN", "NOT_APPLICABLE"}]
    if not present and not profile["lint_tools"] and not profile["precommit"]:
        if not _primary_langs(profile):
            return _na("Q06", "No languages to lint or format.")
        return _result(
            "Q06",
            status="FAIL",
            summary="No linter/formatter config found. Q06 is the LT overview and does not add a separate score.",
            observations={"from_checks": OVERVIEW_IDS, "lt_status": lt_status},
            evidence={"paths": []},
            evidence_flags={"declared": False},
            remediation="Add a suitable linter, cover the source, and fail CI on the agreed threshold (LT01–LT11).",
        )
    if "FAIL" in known:
        status = "FAIL"
    elif "WARN" in known:
        status = "WARN"
    elif known:
        status = "PASS"
    elif present and all(s == "NOT_APPLICABLE" for s in present):
        status = "NOT_APPLICABLE"
    else:
        status = "UNKNOWN"
    parts = [f"{cid}={st or 'pending'}" for cid, st in lt_status.items()]
    extra = ""
    if not profile["ci_paths"] and status != "NOT_APPLICABLE":
        extra = " Local hook without CI is only extra feedback."
    summary = "Lint overview from LT01/LT02/LT05/LT09/LT10/LT11: " + ", ".join(parts) + "." + extra
    rem = None
    if status == "FAIL":
        rem = "Fix failing LT lint checks: tool coverage, config, scope, CI run, result, and merge gate."
    elif status == "WARN":
        rem = "Tighten CI execution and merge-gate evidence; Q06 does not add a second score."
    elif status == "UNKNOWN":
        rem = "Provide CI job/report evidence for the evaluated revision."
    return _result(
        "Q06",
        status=status if status != "NOT_APPLICABLE" else "NOT_APPLICABLE",
        summary=summary,
        observations={"from_checks": list(OVERVIEW_IDS), "lt_status": lt_status, "scoring_enabled": False},
        evidence={"paths": _tool_paths(profile)[:15]},
        evidence_flags={"declared": bool(profile["lint_tools"] or profile["precommit"]), "observed": False},
        reason_code="NOT_APPLICABLE" if status == "NOT_APPLICABLE" else None,
        remediation=rem,
        data_quality={"complete": status not in {"UNKNOWN"}, "missing_sources": ["gitlab_api"] if status == "UNKNOWN" else []},
    )


LT_RUNNERS = {
    "LT01": check_lt01,
    "LT02": check_lt02,
    "LT03": check_lt03,
    "LT04": check_lt04,
    "LT05": check_lt05,
    "LT06": check_lt06,
    "LT07": check_lt07,
    "LT08": check_lt08,
    "LT09": check_lt09,
    "LT10": check_lt10,
    "LT11": check_lt11,
    "LT12": check_lt12,
    "LT13": check_lt13,
    "LT14": check_lt14,
    "LT15": check_lt15,
    "LT16": check_lt16,
}
