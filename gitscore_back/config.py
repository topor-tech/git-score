from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GIT_EXECUTABLE = os.environ.get("GIT_EXECUTABLE", "git")
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data")).resolve()
DB_PATH = DATA_DIR / "git-score.db"
CLONES_DIR = DATA_DIR / "clones"

OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

UI_FILE_BYTES = 512 * 1024
UI_FILE_LINES = 2000
LLM_FILE_BYTES = 32 * 1024
LLM_FILE_LINES = 400
SEARCH_HIT_CAP = 50
GIT_LOG_CAP = 30
COMMIT_HISTORY_CAP = 2000
CONTRIBUTOR_CAP = 50
TOOL_ROUND_CAP = 8

HIDDEN_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "vendor",
    "target",
    ".idea",
    ".cursor",
    ".next",
    "coverage",
}
