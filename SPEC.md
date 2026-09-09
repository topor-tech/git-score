# Git Score — product spec (v1)

A local website that analyzes a git repository into a list of independent checks, lets you browse the working copy in the browser, and chats with an LLM grounded in those checks and files.

This is the product source of truth. Implementation details live in [ARCHITECTURE.md](ARCHITECTURE.md).

## Vision

Judging a repo’s health (activity, bus factor, hygiene, risk) is slow if you have to poke around by hand. Git Score runs a fixed set of **deterministic checks**, shows **evidence**, and lets you **ask why** — without inventing a single weighted “overall score.”

This is not a general coding assistant. The primary objects are the **check list** and a **read-only file tree**. Chat explains checks, cites evidence, and suggests how to improve weak results. Opening a file is how you inspect evidence yourself. Free-form code Q&A is a follow-up, not the main job.

## Audience and constraints

- **v1 audience:** one person on their own machine (a local demo).
- **No** login, multi-tenant SaaS, or private GitHub OAuth.
- **Git for Windows** (or Git on PATH) is a required runtime.
- LLM credentials live in `.env` only — not in the UI.

## Out of scope (v1)

Deferred on purpose:

- Weighted overall score, dimension rollups, letter grades, editable weights
- Accounts, sharing links, multi-user
- GitHub OAuth, private remotes, PR/issue signals, stars, Dependabot/CVE
- LLM-generated architecture wiki
- Repo comparison, score over time, README badges
- Full semantic code index / “explain this function” as the main job
- Real secret-scanning (entropy tools); v1 only flags obvious credential-like **filenames**
- In-browser edit/save/commit, git blame, diffs, image preview beyond a placeholder
- Mobile-first layout

## User flow

1. Open the app. Paste a **local path** or a **clone URL**.
2. Analysis runs with visible progress (clone if needed, then each check).
3. The **repo tree** is usable as soon as the working copy exists, even while checks still run.
4. The **check list** appears as checks complete (grouped by category for reading only). Each row: name, score, one-line why; expand for evidence. Evidence **paths are clickable** and open the file viewer.
5. **Chat** is available once the check run has finished. Suggested prompts come from failing or low-scoring checks. Citation chips open the same file viewer.
6. Re-running on the same source creates a **new snapshot**. Previous chat stays attached to the old snapshot.

There is **no overall score** and **no category rollup**. Categories are labels, not scores.

## Check model

- Checks are **independent**. No weights, no average, no letter grade.
- Each check score is either:
  - **binary:** `0` or `1` (fail / pass), or
  - **ratio:** a float in `[0.0, 1.0]` inclusive.
- Scores are **deterministic**: same commit snapshot → same numbers. The LLM must not invent or adjust scores.
- Every check has **evidence** (paths, SHAs, author names, counts) that the UI and chat can cite.
- Signals come from **git + the filesystem**. Hosted-forge APIs are out of v1.
- This is a heuristic health check, not a code-quality oracle. The product should say so.

### Result shape

Each check result includes at least:

| Field | Meaning |
| --- | --- |
| `id` | Stable machine id (`has_readme`, `bus_factor`, …) |
| `title` | Human name |
| `category` | Grouping label only: `hygiene`, `activity`, `community`, `structure`, `risk` |
| `score` | `0`/`1` or `0.0`–`1.0` |
| `score_kind` | `binary` or `ratio` |
| `summary` | One-line explanation |
| `evidence` | Structured facts (paths, SHAs, counts, samples) |

The UI shows binary as pass/fail and ratios as a bar or percentage. It must not compute a composite number from them.

If the user asks for an overall/weighted score, the product (UI copy and the model) says v1 does not compute one and talks about individual checks instead.

If the user asks to change a check score, refuse: they can change the repo and re-run.

### Catalog (v1)

Ids and formulas below are the intended defaults. Tweaking thresholds at implementation is allowed if documented here afterward.

**Hygiene (binary)**

- `has_readme` — README at repo root (`README`, `README.md`, `README.rst`, `README.txt`; case-insensitive).
- `has_license` — `LICENSE`, `LICENSE.md`, `COPYING`, or `COPYING.md` at root.
- `has_gitignore` — `.gitignore` at root.
- `has_ci` — common CI config present (e.g. `.github/workflows/*.{yml,yaml}`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `Jenkinsfile`, `.circleci/config.yml`).
- `has_contributing` — `CONTRIBUTING` or `CONTRIBUTING.md` at root.
- `has_tags` — at least one git tag.

**Activity (ratio)**

- `last_commit_recency` — `1.0` if HEAD is ≤ 7 days old; linear decay to `0.0` at 365 days (and 0 beyond).
- `commit_volume_90d` — `min(1.0, commits_in_last_90_days / 50)`.

**Community (ratio)**

- `bus_factor` — `1.0 - (commits_by_top_author / total_commits)` on the default history (empty repo → `0`).
- `active_authors_90d` — `min(1.0, distinct_authors_last_90_days / 5)`.

**Structure (mix)**

- `has_tests` — binary: a conventional test tree or test-named files exist (`test/`, `tests/`, `__tests__/`, `spec/`, `*_test.py`, `*.test.*`, `*.spec.*`).
- `test_file_ratio` — test files / (test files + source files), already in `[0, 1]`; `0` if no source files.
- `no_oversized_files` — start at `1.0`; subtract `0.2` per working-tree file larger than 1 MiB (floor `0`). Skip hidden/generated dirs listed in architecture.

**Risk (mix)**

- `no_huge_blobs` — `1.0` if no tracked/working-tree file ≥ 10 MiB; else `max(0, 1.0 - 0.25 * count)`.
- `commit_message_quality` — fraction of commits whose subject is non-empty and ≥ 10 characters (sample or full history — document the cap in architecture).
- `no_credential_filenames` — `1` if no path matches obvious secret names (`.env`, `*.pem`, `id_rsa`, `credentials.json`, etc.); `0` if any match. **Never** put file contents of those paths into chat.

## UI

After a repo is loaded, three regions on one page:

1. **Checks** — source picker, check list grouped by category, weak-first sort, expandable evidence. No overall number. Clicking a path selects it in the tree and opens the file.
2. **Repo** — collapsible directory tree + read-only file viewer (syntax highlighting for common text types). Web view of the working copy, not an editor. Tree as a narrow sidebar inside this pane.
3. **Chat** — suggested prompts, streaming answer, citation chips that open the repo pane to that path.

Desktop three-column layout (`checks | tree+file | chat`). Exact split can change; all three must be reachable without leaving the analysis page.

Before analysis: landing form (path or URL) and a list of recent local analyses.

### Repo tree and file viewer

- Lazy-load one directory’s children on expand. Do not upload the whole monorepo tree up front.
- Hide by default: `.git`, `node_modules`, `__pycache__`, `dist`, `build`, `.venv`, and other heavy/generated dirs (show-hidden is later).
- **Read-only.** No edit, save, or commit in v1.
- Text: line numbers, basic highlighting, size/line cap, notice if truncated.
- Binary or oversized: placeholder (`binary` / `too large`); no hex dump.
- Breadcrumb of the current path. Copy-path is nice-to-have.
- Clicking check evidence or a chat path citation opens the same viewer.

The human viewer may show more of a file than the model is allowed to see. The LLM cap stays stricter.

## Chat

The model receives the full check-result JSON plus a short repo summary. It must use tools instead of guessing repo facts.

**Tools**

- `get_checks` — full check list
- `get_check_evidence(check_id)` — evidence for one check
- `list_contributors` — authors, commit counts, last active
- `list_dir(path)` — directory listing (same hiding rules as the tree UI)
- `search_files(query)` — path/name search, capped
- `read_file(path)` — small files only; stricter size/line cap than the human viewer
- `git_log(path_or_author)` — recent commits, capped

**Rules**

- Stream tokens.
- Cite evidence (`check id`, path, SHA). Never claim a score that is not in the JSON.
- Path citations are clickable in the UI.
- No overall score narrative.
- Chat history is stored with that analysis snapshot (survives refresh).
- Suggested starters from weak checks, e.g. “Why did `has_ci` fail?” / “How do I improve `bus_factor`?”

## Success criteria (v1)

- Analyze a local clone of a mid-size public repo in a couple of minutes on a laptop.
- Every check is explainable: expand it and see evidence, not just a number.
- Chat can answer “why did this check fail / score low?” with citations that match the dashboard.
- You can browse the repo tree and open a text file; check evidence paths and chat citations open that file.
- No overall/weighted score is shown or computed.
- Re-running the same source creates a new snapshot; old chat stays on the old snapshot.
- Works on Windows with Git on PATH.
