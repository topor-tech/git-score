from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR, DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    working_copy TEXT,
                    head_sha TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    checks_json TEXT,
                    progress TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_analysis
                    ON messages(analysis_id, created_at);
                """
            )
            self._conn.commit()
            try:
                self._conn.execute("ALTER TABLE analyses ADD COLUMN progress TEXT")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass

    def create_analysis(
        self,
        analysis_id: str,
        source_type: str,
        source: str,
        status: str = "queued",
    ) -> dict[str, Any]:
        row = {
            "id": analysis_id,
            "source_type": source_type,
            "source": source,
            "working_copy": None,
            "head_sha": None,
            "status": status,
            "error": None,
            "checks_json": None,
            "created_at": _now(),
            "completed_at": None,
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO analyses (
                    id, source_type, source, working_copy, head_sha,
                    status, error, checks_json, created_at, completed_at
                ) VALUES (
                    :id, :source_type, :source, :working_copy, :head_sha,
                    :status, :error, :checks_json, :created_at, :completed_at
                )
                """,
                row,
            )
            self._conn.commit()
        return row

    def update_analysis(self, analysis_id: str, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [analysis_id]
        with self._lock:
            self._conn.execute(
                f"UPDATE analyses SET {assignments} WHERE id = ?",
                values,
            )
            self._conn.commit()

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def list_analyses(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def add_message(self, msg_id: str, analysis_id: str, role: str, content: str) -> dict[str, Any]:
        row = {
            "id": msg_id,
            "analysis_id": analysis_id,
            "role": role,
            "content": content,
            "created_at": _now(),
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO messages (id, analysis_id, role, content, created_at)
                VALUES (:id, :analysis_id, :role, :content, :created_at)
                """,
                row,
            )
            self._conn.commit()
        return row

    def list_messages(self, analysis_id: str) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM messages
                WHERE analysis_id = ?
                ORDER BY created_at ASC
                """,
                (analysis_id,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]
