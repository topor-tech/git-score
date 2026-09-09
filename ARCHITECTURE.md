# Git Score — architecture (v1)

Companion to [SPEC.md](SPEC.md). This describes stack, data, Git access, APIs, LLM tools, and safety. It is not an implementation yet.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Python, FastAPI |
| Frontend | Vite + React + TypeScript |
| Storage | SQLite (analyses, check JSON, chat messages) |
| Clones | `data/` working copies (gitignored) |
| LLM | OpenAI-compatible HTTP API (OpenAI, OpenRouter, Groq, Ollama) via `.env` |
| Git | **Git CLI on PATH** (subprocess). No GitPython, pygit2, or Dulwich in v1. |

Python owns checks, Git, file serving, and chat streaming. The SPA owns the three-pane UI.

Git is a **required runtime** (Git for Windows on this machine). GitPython still shells out to `git` and does not remove that dependency. pygit2 would replace Git but makes Windows installs and some stats harder. Dulwich is too weak for clone + history checks.

## Proposed repo layout

```
backend/          # FastAPI app
web/               # Vite + React
data/              # clones + sqlite (not in git)
SPEC.md
ARCHITECTURE.md
```

Exact package names can change at implementation.

## Git CLI

Thin helpers around `subprocess`. Prefer **plumbing** over porcelain.

**Conventions (always)**

- `git -C <repo>` for an existing working copy
- `--no-pager`
- `-c core.quotepath=false`
- `GIT_TERMINAL_PROMPT=0` (and related env) so clone never blocks on credentials
- NUL-delimited path lists (`-z` / `-0`) when paths can contain spaces or non-ASCII
- No interactive flags; timeouts on every call

**Commands we expect to use**

- Clone: `git clone` into `data/clones/<analysis_id>/`
- Checks: `rev-list`, `log --format=...`, `shortlog`, `tag`, `ls-files -z`
- Do **not** use `git show` / `git cat-file` for the file viewer

**Filesystem for tree and files.** After the working copy exists, `list_dir` and `read_file` walk the checkout. Git is for history and clone only.

## Analysis job

Model analysis as a **job** even if small repos finish quickly, so the UI can poll or stream progress per check.

```
queued → cloning (if URL) → running_checks → complete
                              ↘ failed
```

- Local path: analyze in place **or** copy — prefer analyzing the given path read-only; do not mutate the user’s repo (no checkout, no clean).
- URL: clone into `data/clones/<id>/`. Shallow clone is allowed if history checks still have enough commits for 90-day windows; if shallow breaks recency/volume, deepen or do a full clone. Document the choice in code comments when implemented.
- Record the resolved HEAD SHA on the analysis row so a snapshot is reproducible.
- Skip walking `node_modules`, `.git`, `__pycache__`, `dist`, `build`, `.venv`, and similar when scanning files for structure/risk checks (same hide-list as the tree).

Re-run = **new analysis id**. Old rows and chat stay.

## Data model

SQLite is enough for a local demo.

### `analyses`

| Column | Notes |
| --- | --- |
| `id` | UUID |
| `source_type` | `path` or `url` |
| `source` | Original path or clone URL |
| `working_copy` | Absolute path used for git + files |
| `head_sha` | Resolved commit, nullable until clone/open succeeds |
| `status` | `queued`, `cloning`, `running_checks`, `complete`, `failed` |
| `error` | Failure message |
| `checks_json` | Full check-result array (see spec shape) once available; may be partial while running |
| `created_at` / `completed_at` | ISO timestamps |

### `messages`

| Column | Notes |
| --- | --- |
| `id` | UUID |
| `analysis_id` | FK |
| `role` | `user` / `assistant` / `system` / `tool` as needed |
| `content` | Text or JSON |
| `created_at` | |

Optional later: a `check_runs` table for per-check status. v1 can stream progress via job status + appending to `checks_json`.

### Check JSON

Array of objects matching SPEC.md (`id`, `title`, `category`, `score`, `score_kind`, `summary`, `evidence`). `evidence` is JSON (e.g. `{ "paths": [], "commits": [], "counts": {} }`). No `overall_score` field anywhere.

## HTTP API (sketch)

Prefix can be `/api`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/analyses` | Body: `{ "source": "<path-or-url>" }`. Returns analysis id + status. |
| `GET` | `/analyses` | Recent analyses for the landing page. |
| `GET` | `/analyses/{id}` | Status, metadata, checks (when present). |
| `GET` | `/analyses/{id}/tree?path=` | Directory listing. Default `path` = repo root. |
| `GET` | `/analyses/{id}/file?path=` | File metadata + text (or binary/too-large flags). |
| `GET` | `/analyses/{id}/messages` | Chat history. |
| `POST` | `/analyses/{id}/chat` | User message; response is **SSE** token stream. |

Progress: `GET /analyses/{id}` polling is enough for v1; SSE for analysis progress is optional.

### Tree listing payload

```json
{
  "path": "src",
  "entries": [
    { "name": "auth", "kind": "dir" },
    { "name": "main.ts", "kind": "file", "size": 1204 }
  ]
}
```

Omit hidden/generated names by default. Reject paths that escape the working copy (`..`, absolute paths, symlink escape). Resolve with `Path.resolve` / equivalent and require `relative_to(working_copy)`.

### File payload

```json
{
  "path": "README.md",
  "kind": "text",
  "size": 2048,
  "truncated": false,
  "content": "..."
}
```

`kind` is `text` | `binary` | `too_large`. Human viewer cap (starting defaults): **512 KiB** or **2000 lines**, whichever hits first. Binary detection: NUL byte or well-known extensions.

## LLM tools and safety

Chat endpoint: load `checks_json` + short summary (source, HEAD SHA, language mix if cheap) into the system prompt. Expose tools that call the same helpers as the HTTP tree/file APIs.

| Tool | Behavior |
| --- | --- |
| `get_checks` | Return the check array |
| `get_check_evidence` | One check’s `evidence` + `summary` |
| `list_contributors` | From `git shortlog` / `log`, capped (e.g. top 50) |
| `list_dir` | Same as `GET .../tree` |
| `search_files` | Filename/path substring, max N hits (e.g. 50), skip hidden dirs |
| `read_file` | **Stricter cap than UI**, e.g. 32 KiB or 400 lines; redact lines that look like secrets (`AKIA…`, `-----BEGIN`, `api_key=`) before returning to the model |
| `git_log` | Capped (e.g. 30 commits); optional path or author filter |

**Do not** send the whole repo to the model. **Do not** return contents of credential-like paths to the model even if the user asks; point at the `no_credential_filenames` check instead.

Streaming: SSE (or fetch + `text/event-stream`) from FastAPI to the SPA.

## Frontend

Three columns after load: checks | tree + viewer | chat.

- Tree: expand → `GET .../tree?path=`
- File click / citation → `GET .../file?path=`
- Checks from `GET .../analyses/{id}`
- Chat: POST + stream; persist via `messages` so refresh restores the thread

No auth UI. Missing LLM config: show a clear error pointing at `.env` (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` or equivalent).

## Environment

```
OPENAI_BASE_URL=
OPENAI_API_KEY=
OPENAI_MODEL=
GIT_EXECUTABLE=git
DATA_DIR=./data
```

`GIT_EXECUTABLE` lets Windows users point at `git.exe` if it is not on PATH.

## Non-goals in this architecture

Same as SPEC.md deferred list. In particular: no weight config table, no overall score column, no OAuth, no pygit2.
