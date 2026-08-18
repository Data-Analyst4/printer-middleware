import os
import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager
from app.models.job import JobStatus

class DatabaseManager:
    def __init__(self, db_path="app/db/jobs.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    printer_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER DEFAULT 2,
                    commands TEXT NOT NULL,
                    responses TEXT DEFAULT '[]',
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 5,
                    next_retry_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS printers (
                    printer_id TEXT PRIMARY KEY,
                    ip TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    last_seen TEXT,
                    created_at TEXT NOT NULL
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'operator',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')

            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_jobs_printer ON jobs(printer_id)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_jobs_next_retry ON jobs(next_retry_at)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)
            ''')

    @contextmanager
    def get_connection(self):
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

    def create_job(self, job_id, printer_id, commands, priority=2):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO jobs (job_id, printer_id, status, priority, commands, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (job_id, printer_id, JobStatus.QUEUED.value, priority, json.dumps(commands), now, now))

    def get_job(self, job_id):
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
            return dict(row) if row else None

    def update_job_status(self, job_id, status, error=None, responses=None, retry_count=None, next_retry_at=None):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            row = conn.execute('SELECT responses FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
            current_responses = json.loads(row['responses'] or '[]') if row else []

            if responses is not None:
                # replace with provided list
                current_responses = responses

            conn.execute('''
                UPDATE jobs
                SET status = ?,
                    updated_at = ?,
                    error = ?,
                    responses = ?,
                    retry_count = COALESCE(?, retry_count),
                    next_retry_at = COALESCE(?, next_retry_at)
                WHERE job_id = ?
            ''', (
                status.value if hasattr(status, 'value') else status,
                now,
                error,
                json.dumps(current_responses),
                retry_count,
                next_retry_at,
                job_id
            ))

    def get_pending_jobs(self, printer_id=None, limit=10):
        query = '''
            SELECT * FROM jobs
            WHERE status IN (?, ?, ?)
            AND (next_retry_at IS NULL OR next_retry_at <= ?)
        '''
        params = [JobStatus.QUEUED.value, JobStatus.PROCESSING.value, JobStatus.RETRYING.value, datetime.now().isoformat()]

        if printer_id:
            query += ' AND printer_id = ?'
            params.append(printer_id)

        query += ' ORDER BY priority ASC, created_at ASC LIMIT ?'
        params.append(limit)

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_all_jobs(self, limit=100):
        with self.get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?
            ''', (limit,)).fetchall()
            return [dict(row) for row in rows]

    def get_jobs_by_status(self, status):
        with self.get_connection() as conn:
            rows = conn.execute('SELECT * FROM jobs WHERE status = ?', (status,)).fetchall()
            return [dict(row) for row in rows]

    def get_metrics(self):
        with self.get_connection() as conn:
            result = conn.execute('''
                SELECT
                    COUNT(*) as total_jobs,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as queued_jobs,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as processing_jobs,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as completed_jobs,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as failed_jobs
                FROM jobs
            ''', (JobStatus.QUEUED.value, JobStatus.PROCESSING.value,
                  JobStatus.COMPLETED.value, JobStatus.FAILED.value)).fetchone()
            return dict(result)

    def register_printer(self, printer_id, ip, port):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO printers (printer_id, ip, port, last_seen, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (printer_id, ip, port, now, now))

    def get_printers(self):
        with self.get_connection() as conn:
            rows = conn.execute('SELECT * FROM printers WHERE is_active = 1').fetchall()
            return [dict(row) for row in rows]

    def update_printer_status(self, printer_id, last_seen=None):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE printers SET last_seen = ? WHERE printer_id = ?
            ''', (last_seen or now, printer_id))
