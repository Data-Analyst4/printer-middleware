"""Job and print-item persistence."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import Settings


class JobStore:
    STATUSES = ("queued", "processing", "completed", "failed", "rejected")

    def __init__(self, settings: Settings):
        self.settings = settings
        self.db_path = Path(settings.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS print_items (
                    item_id TEXT PRIMARY KEY,
                    printer_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER DEFAULT 2,
                    command TEXT NOT NULL,
                    erp_ref TEXT,
                    response TEXT,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_items_printer_status
                    ON print_items(printer_id, status, priority, created_at);
                CREATE TABLE IF NOT EXISTS sync_results (
                    job_id TEXT PRIMARY KEY,
                    printer_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sync_created ON sync_results(created_at DESC);
                """
            )

    def enqueue_item(
        self,
        printer_id: str,
        command: Dict[str, Any],
        priority: int = 2,
        erp_ref: Optional[str] = None,
    ) -> str:
        item_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO print_items
                (item_id, printer_id, status, priority, command, erp_ref, created_at, updated_at)
                VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)
                """,
                (item_id, printer_id, priority, json.dumps(command), erp_ref, now, now),
            )
        return item_id

    def count_queued(self, printer_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM print_items WHERE printer_id = ? AND status IN ('queued', 'processing')",
                (printer_id,),
            ).fetchone()
            return int(row["c"]) if row else 0

    def queue_depths(self) -> Dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT printer_id, COUNT(*) AS c
                FROM print_items
                WHERE status IN ('queued', 'processing')
                GROUP BY printer_id
                """
            ).fetchall()
            return {row["printer_id"]: int(row["c"]) for row in rows}

    def fetch_next(self, printer_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM print_items
                WHERE printer_id = ? AND status = 'queued'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """,
                (printer_id,),
            ).fetchone()
            if not row:
                return None
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE print_items SET status = 'processing', updated_at = ? WHERE item_id = ?",
                (now, row["item_id"]),
            )
            return dict(row)

    def complete_item(self, item_id: str, response: Dict[str, Any], ok: bool) -> None:
        now = datetime.now().isoformat()
        status = "completed" if ok else "failed"
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE print_items
                SET status = ?, response = ?, error = ?, updated_at = ?, completed_at = ?
                WHERE item_id = ?
                """,
                (
                    status,
                    json.dumps(response),
                    None if ok else response.get("reason"),
                    now,
                    now,
                    item_id,
                ),
            )

    def requeue_failed(self, item_id: str, error: str, retry_count: int) -> None:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE print_items
                SET status = 'queued', error = ?, retry_count = ?, updated_at = ?
                WHERE item_id = ?
                """,
                (error, retry_count, now, item_id),
            )

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM print_items WHERE item_id = ?", (item_id,)).fetchone()
            return self._row_to_item(row) if row else None

    def list_items(self, printer_id: Optional[str] = None, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = "SELECT * FROM print_items WHERE 1=1"
        params: List[Any] = []
        if printer_id:
            query += " AND printer_id = ?"
            params.append(printer_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_item(row) for row in rows]

    def save_sync_result(self, job_id: str, printer_id: str, status: str, payload: Dict[str, Any]) -> None:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sync_results (job_id, printer_id, status, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, printer_id, status, json.dumps(payload), now, now),
            )

    def get_sync_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM sync_results WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return None
            payload = json.loads(row["payload"])
            return {"success": True, "job_id": row["job_id"], **payload}

    def list_sync_results(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM sync_results ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def metrics(self) -> Dict[str, int]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_jobs,
                    SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) AS queued_jobs,
                    SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) AS processing_jobs,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_jobs,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_jobs,
                    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_jobs
                FROM print_items
                """
            ).fetchone()
            sync_total = conn.execute("SELECT COUNT(*) AS c FROM sync_results").fetchone()
            result = dict(row)
            result["sync_total"] = int(sync_total["c"]) if sync_total else 0
            return {key: int(result[key] or 0) for key in result.keys()}

    def purge_old(self) -> None:
        cutoff = (datetime.now() - timedelta(hours=self.settings.result_ttl_hours)).isoformat()
        with self._conn() as conn:
            conn.execute("DELETE FROM sync_results WHERE created_at < ?", (cutoff,))
            conn.execute(
                "DELETE FROM print_items WHERE status IN ('completed', 'failed') AND completed_at < ?",
                (cutoff,),
            )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["command"] = json.loads(item["command"])
        if item.get("response"):
            item["response"] = json.loads(item["response"])
        return item
