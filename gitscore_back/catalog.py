"""Stable catalog for the checks in docs/repository-checks/checks.md."""

from __future__ import annotations

import re

GROUPS: dict[str, dict[str, str]] = {
    "R": {"title": "Git integrity and hygiene", "title_ru": "Целостность и гигиена Git"},
    "D": {"title": "Documentation, ownership, governance", "title_ru": "Документация, ownership и управление"},
    "G": {"title": "History protection and change control", "title_ru": "Защита истории и управление изменениями"},
    "Q": {"title": "CI, tests, and code quality", "title_ru": "CI, тестирование и качество кода"},
    "LT": {"title": "Linting and linters", "title_ru": "Линтинг и линтеры"},
    "S": {"title": "Security and software supply chain", "title_ru": "Безопасность и software supply chain"},
    "L": {"title": "Releases and reproducibility", "title_ru": "Релизы и воспроизводимость"},
    "T": {"title": "Team and actual process", "title_ru": "Команда и фактический процесс"},
}

_ID_GROUP = re.compile(r"^([A-Z]+)\d+")

# evaluation_mode: policy (PASS/WARN/FAIL) or observation (status null).
# sources: git, fs, gitlab_api, ci_artifacts, registry, deployments
CHECKS: list[dict] = [
    {"id": "R01", "title": "Git object integrity", "tags": ["reliability"], "importance": 5, "evaluation_mode": "policy", "sources": ["git"], "check_type": "state"},
    {"id": "R02", "title": "Valid default branch", "tags": ["governance"], "importance": 5, "evaluation_mode": "policy", "sources": ["git"], "check_type": "state"},
    {"id": "R03", "title": "Repository size", "tags": ["performance"], "importance": 3, "evaluation_mode": "observation", "sources": ["git"], "check_type": "state"},
    {"id": "R04", "title": "No large tracked files", "tags": ["performance"], "importance": 4, "evaluation_mode": "policy", "sources": ["git"], "check_type": "state"},
    {"id": "R05", "title": "Artifact hygiene", "tags": ["quality", "security"], "importance": 4, "evaluation_mode": "policy", "sources": ["git", "fs"], "check_type": "state"},
    {"id": "R06", "title": "Binary/generated code ratio", "tags": ["maintainability"], "importance": 3, "evaluation_mode": "observation", "sources": ["git", "fs"], "check_type": "state"},
    {"id": "R07", "title": "Valid submodules", "tags": ["supply-chain"], "importance": 4, "evaluation_mode": "policy", "sources": ["git"], "check_type": "state"},
    {"id": "R08", "title": "Repository maintenance", "tags": ["performance"], "importance": 2, "evaluation_mode": "observation", "sources": ["git"], "check_type": "state"},
    {"id": "D01", "title": "Useful README", "tags": ["onboarding"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "D02", "title": "Explicit ownership", "tags": ["resilience"], "importance": 2, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "D03", "title": "CODEOWNERS coverage", "tags": ["review"], "importance": 5, "evaluation_mode": "policy", "sources": ["git", "fs"], "check_type": "state"},
    {"id": "D04", "title": "Contribution guide", "tags": ["process"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "D05", "title": "Security policy", "tags": ["security"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "D06", "title": "Production runbook", "tags": ["operations"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "D07", "title": "Architecture documentation", "tags": ["maintainability"], "importance": 3, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "D08", "title": "License declared", "tags": ["licensing", "supply-chain"], "importance": 2, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "D09", "title": "MR/issue templates", "tags": ["process"], "importance": 3, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "D10", "title": "Service metadata", "tags": ["operations"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "G01", "title": "Protected default branch", "tags": ["security"], "importance": 5, "evaluation_mode": "policy", "sources": ["gitlab_api"], "check_type": "state"},
    {"id": "G02", "title": "MR-only changes", "tags": ["review"], "importance": 5, "evaluation_mode": "policy", "sources": ["gitlab_api"], "check_type": "state"},
    {"id": "G03", "title": "Independent approval", "tags": ["security"], "importance": 5, "evaluation_mode": "policy", "sources": ["gitlab_api"], "check_type": "state"},
    {"id": "G04", "title": "Fresh approval", "tags": ["review"], "importance": 4, "evaluation_mode": "policy", "sources": ["gitlab_api"], "check_type": "process"},
    {"id": "G05", "title": "Required CODEOWNER review", "tags": ["ownership"], "importance": 5, "evaluation_mode": "policy", "sources": ["gitlab_api", "fs"], "check_type": "state"},
    {"id": "G06", "title": "Required status checks", "tags": ["ci", "quality"], "importance": 5, "evaluation_mode": "policy", "sources": ["gitlab_api"], "check_type": "state"},
    {"id": "G07", "title": "Protected CI configuration", "tags": ["supply-chain", "ownership"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs", "gitlab_api"], "check_type": "state"},
    {"id": "G08", "title": "Immutable release tags", "tags": ["release", "supply-chain"], "importance": 4, "evaluation_mode": "policy", "sources": ["gitlab_api"], "check_type": "state"},
    {"id": "G09", "title": "Verified commit identity", "tags": ["audit"], "importance": 3, "evaluation_mode": "policy", "sources": ["git", "gitlab_api"], "check_type": "state"},
    {"id": "G10", "title": "Change traceability", "tags": ["process"], "importance": 3, "evaluation_mode": "policy", "sources": ["git"], "check_type": "process"},
    {"id": "G11", "title": "Consistent merge strategy", "tags": ["release"], "importance": 3, "evaluation_mode": "observation", "sources": ["git"], "check_type": "process"},
    {"id": "G12", "title": "Stale branch control", "tags": ["hygiene"], "importance": 2, "evaluation_mode": "observation", "sources": ["git"], "check_type": "state"},
    {"id": "Q01", "title": "CI on every MR", "tags": ["process"], "importance": 5, "evaluation_mode": "policy", "sources": ["gitlab_api", "fs"], "check_type": "process"},
    {"id": "Q02", "title": "Automated tests", "tags": ["testing"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs", "ci_artifacts"], "check_type": "process"},
    {"id": "Q03", "title": "Default branch green", "tags": ["stability"], "importance": 5, "evaluation_mode": "policy", "sources": ["gitlab_api"], "check_type": "state"},
    {"id": "Q04", "title": "Coverage reporting", "tags": ["testing"], "importance": 4, "evaluation_mode": "observation", "sources": ["fs", "ci_artifacts"], "check_type": "process"},
    {"id": "Q05", "title": "Flaky test rate", "tags": ["stability"], "importance": 5, "evaluation_mode": "observation", "sources": ["ci_artifacts"], "check_type": "trend"},
    {"id": "Q06", "title": "Lint and formatting", "tags": ["quality"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state", "scoring_enabled": False},
    {"id": "Q07", "title": "Type/static checks", "tags": ["quality"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "Q08", "title": "SAST present", "tags": ["security"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "Q09", "title": "Complexity and duplication", "tags": ["maintainability"], "importance": 3, "evaluation_mode": "observation", "sources": ["fs"], "check_type": "trend"},
    {"id": "Q10", "title": "CI feedback time", "tags": ["efficiency"], "importance": 4, "evaluation_mode": "observation", "sources": ["gitlab_api"], "check_type": "trend"},
    {"id": "LT01", "title": "Language and linter coverage", "tags": ["quality"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT02", "title": "Effective configuration declared", "tags": ["quality"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT03", "title": "Configuration resolves successfully", "tags": ["quality"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT04", "title": "Meaningful rules enabled", "tags": ["quality"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT05", "title": "Source scope is covered", "tags": ["quality"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT06", "title": "Reproducible toolchain", "tags": ["quality", "reproducibility"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT07", "title": "Documented local lint command", "tags": ["process", "quality"], "importance": 3, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT08", "title": "Local hook integration", "tags": ["process", "quality"], "importance": 3, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT09", "title": "Lint runs in CI for relevant changes", "tags": ["ci", "quality"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs", "gitlab_api"], "check_type": "process"},
    {"id": "LT10", "title": "Lint passes on evaluated revision", "tags": ["quality"], "importance": 5, "evaluation_mode": "policy", "sources": ["ci_artifacts"], "check_type": "process"},
    {"id": "LT11", "title": "Lint failure blocks merge", "tags": ["ci", "quality"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs", "gitlab_api"], "check_type": "state"},
    {"id": "LT12", "title": "Formatting checked separately", "tags": ["quality"], "importance": 3, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT13", "title": "Local and CI policies agree", "tags": ["process", "quality"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT14", "title": "Suppressions and baseline controlled", "tags": ["quality"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT15", "title": "Actionable lint reports", "tags": ["quality"], "importance": 3, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "LT16", "title": "Lint policy changes reviewed", "tags": ["review", "quality"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "S01", "title": "Secret scanning", "tags": ["security"], "importance": 5, "evaluation_mode": "policy", "sources": ["git", "fs"], "check_type": "state"},
    {"id": "S02", "title": "Push secret protection", "tags": ["security"], "importance": 5, "evaluation_mode": "policy", "sources": ["gitlab_api"], "check_type": "state"},
    {"id": "S03", "title": "Vulnerable dependencies", "tags": ["dependencies"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs", "registry"], "check_type": "state"},
    {"id": "S04", "title": "Automated dependency updates", "tags": ["maintainability"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "S05", "title": "Dependency age", "tags": ["maintainability"], "importance": 4, "evaluation_mode": "observation", "sources": ["registry"], "check_type": "state"},
    {"id": "S06", "title": "Deterministic dependency resolution", "tags": ["reproducibility"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "S07", "title": "Pinned CI dependencies", "tags": ["ci"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "S08", "title": "Least CI permissions", "tags": ["ci"], "importance": 5, "evaluation_mode": "policy", "sources": ["gitlab_api", "fs"], "check_type": "state"},
    {"id": "S09", "title": "Dangerous workflow detection", "tags": ["ci"], "importance": 5, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "S10", "title": "SBOM generated", "tags": ["release"], "importance": 3, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "S11", "title": "Signed release", "tags": ["release"], "importance": 4, "evaluation_mode": "policy", "sources": ["git", "registry"], "check_type": "state"},
    {"id": "S12", "title": "Build provenance", "tags": ["release"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs", "registry"], "check_type": "state"},
    {"id": "L01", "title": "Reproducible build", "tags": ["supply-chain"], "importance": 4, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "L02", "title": "Release traceability", "tags": ["governance"], "importance": 5, "evaluation_mode": "policy", "sources": ["deployments"], "check_type": "process"},
    {"id": "L03", "title": "Version consistency", "tags": ["release"], "importance": 3, "evaluation_mode": "policy", "sources": ["git", "fs"], "check_type": "state"},
    {"id": "L04", "title": "Release notes", "tags": ["documentation"], "importance": 3, "evaluation_mode": "policy", "sources": ["fs"], "check_type": "state"},
    {"id": "L05", "title": "Commit convention", "tags": ["automation"], "importance": 2, "evaluation_mode": "observation", "sources": ["git"], "check_type": "process"},
    {"id": "L06", "title": "Release frequency", "tags": ["flow"], "importance": 4, "evaluation_mode": "observation", "sources": ["git"], "check_type": "trend"},
    {"id": "T01", "title": "Maintained repository", "tags": ["resilience"], "importance": 4, "evaluation_mode": "observation", "sources": ["git"], "check_type": "trend"},
    {"id": "T02", "title": "Contributor absence factor", "tags": ["ownership"], "importance": 5, "evaluation_mode": "observation", "sources": ["git"], "check_type": "trend"},
    {"id": "T03", "title": "Effective ownership coverage", "tags": ["resilience"], "importance": 5, "evaluation_mode": "observation", "sources": ["git", "fs"], "check_type": "trend"},
    {"id": "T04", "title": "Review coverage", "tags": ["quality"], "importance": 5, "evaluation_mode": "observation", "sources": ["gitlab_api"], "check_type": "process"},
    {"id": "T05", "title": "Self-merge without independent review", "tags": ["governance"], "importance": 4, "evaluation_mode": "observation", "sources": ["gitlab_api"], "check_type": "process"},
    {"id": "T06", "title": "Time to first review", "tags": ["responsiveness"], "importance": 4, "evaluation_mode": "observation", "sources": ["gitlab_api"], "check_type": "trend"},
    {"id": "T07", "title": "MR cycle time", "tags": ["flow"], "importance": 5, "evaluation_mode": "observation", "sources": ["gitlab_api"], "check_type": "trend"},
    {"id": "T08", "title": "Stale MR and WIP", "tags": ["flow"], "importance": 4, "evaluation_mode": "observation", "sources": ["gitlab_api"], "check_type": "state"},
    {"id": "T09", "title": "Change batch size", "tags": ["risk", "review"], "importance": 4, "evaluation_mode": "observation", "sources": ["git"], "check_type": "trend"},
    {"id": "T10", "title": "Throughput trend", "tags": ["flow"], "importance": 4, "evaluation_mode": "observation", "sources": ["git"], "check_type": "trend"},
    {"id": "T11", "title": "Rework/churn", "tags": ["quality"], "importance": 4, "evaluation_mode": "observation", "sources": ["git"], "check_type": "trend"},
    {"id": "T12", "title": "Code hotspots", "tags": ["maintainability"], "importance": 4, "evaluation_mode": "observation", "sources": ["git"], "check_type": "trend"},
    {"id": "T13", "title": "Pipeline reliability", "tags": ["ci"], "importance": 4, "evaluation_mode": "observation", "sources": ["gitlab_api"], "check_type": "trend"},
    {"id": "T14", "title": "Delivery performance", "tags": ["operations"], "importance": 5, "evaluation_mode": "observation", "sources": ["deployments"], "check_type": "trend"},
]

BY_ID = {c["id"]: c for c in CHECKS}
assert len(CHECKS) == 88, len(CHECKS)


def definition(check_id: str) -> dict:
    return BY_ID[check_id]


def group_of(check_id: str) -> str:
    match = _ID_GROUP.match(check_id)
    return match.group(1) if match else check_id[0]


def public_definition(check: dict, wiki: dict | None = None) -> dict:
    gid = group_of(check["id"])
    page = wiki or {}
    return {
        "id": check["id"],
        "title": page.get("title") or check["title"],
        "group": gid,
        "group_title": GROUPS[gid]["title"],
        "group_title_ru": GROUPS[gid]["title_ru"],
        "tags": page.get("tags") or check["tags"],
        "importance": check["importance"],
        "importance_label": page.get("importance_label") or f"{check['importance']}/5",
        "evaluation_mode": check["evaluation_mode"],
        "check_type": check["check_type"],
        "required_sources": check["sources"],
        "scoring_enabled": check.get("scoring_enabled", True),
        "interpretation": page.get("interpretation") or "",
        "implementation": page.get("implementation") or "",
        "notes": page.get("notes") or "",
        "definition_version": "0.1",
    }
