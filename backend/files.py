from __future__ import annotations

import re
from pathlib import Path

from .config import HIDDEN_DIR_NAMES, LLM_FILE_BYTES, LLM_FILE_LINES, UI_FILE_BYTES, UI_FILE_LINES

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".bmp",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp3",
    ".mp4",
    ".webm",
    ".class",
    ".pyc",
    ".pyo",
    ".o",
    ".a",
    ".wasm",
}

def looks_like_credential(rel_path: str) -> bool:
    name = Path(rel_path.replace("\\", "/")).name.lower()
    if name in {"id_rsa", "credentials.json", ".env"}:
        return True
    if name.endswith(".pem"):
        return True
    if name.startswith(".env.") and name != ".env.example":
        return True
    return False

SECRET_LINE_RE = re.compile(
    r"(AKIA[0-9A-Z]{16}|-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----|api[_-]?key\s*[=:])",
    re.IGNORECASE,
)


class PathEscapeError(ValueError):
    pass


def safe_join(root: Path, rel: str | None) -> Path:
    root = root.resolve()
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if rel in ("", "."):
        target = root
    else:
        if Path(rel).is_absolute() or ":" in Path(rel).parts[0]:
            raise PathEscapeError("absolute paths are not allowed")
        target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PathEscapeError("path escapes working copy") from exc
    return target


def rel_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def is_hidden_dir_name(name: str) -> bool:
    return name in HIDDEN_DIR_NAMES


def list_dir(root: Path, rel: str | None) -> dict:
    directory = safe_join(root, rel)
    if not directory.exists():
        raise FileNotFoundError(rel or ".")
    if not directory.is_dir():
        raise NotADirectoryError(rel or ".")
    entries: list[dict] = []
    try:
        children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        raise FileNotFoundError(rel or ".") from exc
    for child in children:
        name = child.name
        if is_hidden_dir_name(name):
            continue
        try:
            resolved = child.resolve()
            resolved.relative_to(root.resolve())
        except (ValueError, OSError):
            continue
        if child.is_dir():
            entries.append({"name": name, "kind": "dir"})
        elif child.is_file():
            try:
                size = child.stat().st_size
            except OSError:
                size = 0
            entries.append({"name": name, "kind": "file", "size": size})
    path = "" if directory == root.resolve() else rel_posix(root, directory)
    return {"path": path, "entries": entries}


def _is_binary(path: Path, sample: bytes) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    return b"\0" in sample


def read_file(
    root: Path,
    rel: str,
    *,
    max_bytes: int = UI_FILE_BYTES,
    max_lines: int = UI_FILE_LINES,
    redact: bool = False,
    allow_credentials: bool = True,
) -> dict:
    path = safe_join(root, rel)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(rel)
    posix = rel_posix(root, path)
    if looks_like_credential(posix) and not allow_credentials:
        return {
            "path": posix,
            "kind": "blocked",
            "size": path.stat().st_size,
            "truncated": False,
            "content": None,
            "notice": "Credential-like path; contents are not sent to the model.",
        }
    size = path.stat().st_size
    if size > max_bytes * 4 and path.suffix.lower() in BINARY_EXTENSIONS:
        return {"path": posix, "kind": "too_large", "size": size, "truncated": True, "content": None}
    with path.open("rb") as fh:
        sample = fh.read(max_bytes + 1)
    if _is_binary(path, sample[:8192]):
        return {"path": posix, "kind": "binary", "size": size, "truncated": False, "content": None}
    truncated = False
    raw = sample
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        text = "\n".join(lines[:max_lines])
        truncated = True
    if redact:
        redacted = []
        for line in text.splitlines():
            if SECRET_LINE_RE.search(line):
                redacted.append("[redacted]")
            else:
                redacted.append(line)
        text = "\n".join(redacted)
    return {
        "path": posix,
        "kind": "text",
        "size": size,
        "truncated": truncated,
        "content": text,
    }


def read_file_for_ui(root: Path, rel: str) -> dict:
    return read_file(root, rel, max_bytes=UI_FILE_BYTES, max_lines=UI_FILE_LINES, redact=False)


def read_file_for_llm(root: Path, rel: str) -> dict:
    return read_file(
        root,
        rel,
        max_bytes=LLM_FILE_BYTES,
        max_lines=LLM_FILE_LINES,
        redact=True,
        allow_credentials=False,
    )


def search_files(root: Path, query: str, limit: int) -> list[str]:
    q = query.strip().lower().replace("\\", "/")
    if not q:
        return []
    hits: list[str] = []
    root = root.resolve()

    def walk(directory: Path) -> None:
        if len(hits) >= limit:
            return
        try:
            children = list(directory.iterdir())
        except OSError:
            return
        for child in children:
            if len(hits) >= limit:
                return
            if child.is_dir():
                if is_hidden_dir_name(child.name):
                    continue
                try:
                    child.resolve().relative_to(root)
                except (ValueError, OSError):
                    continue
                walk(child)
            elif child.is_file():
                try:
                    posix = rel_posix(root, child)
                except ValueError:
                    continue
                if q in posix.lower() or q in child.name.lower():
                    hits.append(posix)

    walk(root)
    return hits
