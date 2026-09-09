"""Wiki pages generated from docs/repository-checks/checks.md."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from gitscore_back.catalog import BY_ID, CHECKS, GROUPS, group_of, public_definition
from gitscore_back.config import ROOT

CHECKS_MD = ROOT / "docs" / "repository-checks" / "checks.md"
APPROACH_MD = ROOT / "docs" / "repository-checks" / "approach.md"

_GROUP_HEAD = re.compile(
    r"^## ([A-Z]+)\.\s+(.+?)\s+[—–-]\s+(\d+)\s+",
    re.M,
)
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _split_cells(line: str) -> list[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [c.strip() for c in raw.split("|")]


def _is_sep(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells if c)


def _parse_tables_and_notes(text: str) -> tuple[dict[str, dict], dict[str, str], str, str]:
    pages: dict[str, dict] = {}
    notes: dict[str, str] = {}
    intro_parts: list[str] = []
    footer_parts: list[str] = []
    current_group: str | None = None
    in_table = False
    note_buf: list[str] = []
    footer = False
    seen_group = False

    def flush_notes() -> None:
        nonlocal note_buf
        if current_group and note_buf:
            notes[current_group] = "\n".join(note_buf).strip()
        note_buf = []

    for line in text.splitlines():
        if line.startswith("## Правила") or line.startswith("## Приоритет"):
            flush_notes()
            footer = True
            in_table = False
            footer_parts.append(line)
            continue
        gmatch = _GROUP_HEAD.match(line)
        if gmatch:
            flush_notes()
            seen_group = True
            current_group = gmatch.group(1)
            in_table = False
            continue
        if footer:
            footer_parts.append(line)
            continue
        if not seen_group:
            intro_parts.append(line)
            continue
        stripped = line.strip()
        if stripped.startswith("|") and "ID" in stripped and "Краткое" in stripped:
            in_table = True
            continue
        if in_table:
            if not stripped.startswith("|"):
                in_table = False
                if stripped:
                    note_buf.append(line)
                continue
            cells = _split_cells(stripped)
            if _is_sep(cells) or (cells and cells[0] == "ID"):
                continue
            if len(cells) < 6:
                continue
            cid, title, tags, interpretation, implementation, importance = cells[:6]
            if not re.fullmatch(r"[A-Z]+\d{2}", cid):
                continue
            pages[cid] = {
                "id": cid,
                "title": title,
                "tags": [t.strip() for t in tags.replace(",", ";").split(";") if t.strip()],
                "interpretation": interpretation,
                "implementation": implementation,
                "importance_label": importance,
            }
            continue
        note_buf.append(line)
    flush_notes()
    intro = "\n".join(intro_parts).strip()
    footer_text = "\n".join(footer_parts).strip()
    return pages, notes, intro, footer_text


@lru_cache(maxsize=1)
def load_markdown_wiki() -> dict:
    if not CHECKS_MD.is_file():
        return {"pages": {}, "notes": {}, "intro": "", "footer": ""}
    text = CHECKS_MD.read_text(encoding="utf-8")
    pages, notes, intro, footer = _parse_tables_and_notes(text)
    return {"pages": pages, "notes": notes, "intro": intro, "footer": footer}


def wiki_index() -> dict:
    md = load_markdown_wiki()
    pages = md["pages"]
    notes = md["notes"]
    groups = []
    for gid, meta in GROUPS.items():
        items = []
        for check in CHECKS:
            if check["id"][0] != gid:
                continue
            items.append(public_definition(check, pages.get(check["id"])))
        groups.append(
            {
                "id": gid,
                "title": meta["title"],
                "title_ru": meta["title_ru"],
                "notes": notes.get(gid, ""),
                "checks": items,
            }
        )
    return {
        "title": "Repository health checks",
        "source": "docs/repository-checks/checks.md",
        "intro": md["intro"],
        "footer": md["footer"],
        "groups": groups,
        "checks": [item for g in groups for item in g["checks"]],
        "approach_path": "docs/repository-checks/approach.md" if APPROACH_MD.is_file() else None,
    }


def wiki_check(check_id: str) -> dict | None:
    check_id = check_id.upper()
    if check_id not in BY_ID:
        return None
    md = load_markdown_wiki()
    page = md["pages"].get(check_id, {})
    body = public_definition(BY_ID[check_id], page)
    gid = group_of(check_id)
    body["group_notes"] = md["notes"].get(gid, "")
    body["neighbors"] = _neighbors(check_id)
    return body


def _neighbors(check_id: str) -> dict:
    ids = [c["id"] for c in CHECKS]
    i = ids.index(check_id)
    return {
        "prev": ids[i - 1] if i > 0 else None,
        "next": ids[i + 1] if i + 1 < len(ids) else None,
    }


def strip_md_links(text: str) -> str:
    return _MD_LINK.sub(r"\1", text)
