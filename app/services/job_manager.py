from app.models.job import Job, JobStatus, JobPriority
from app.db.database import DatabaseManager
from app.utils.logger import log
import threading

class JobManager:
    def __init__(self, db_manager=None):
        self.db = db_manager or DatabaseManager()
        self.lock = threading.Lock()

    def create_job(self, printer_id, commands, priority_str="normal"):
        priority = JobPriority.HIGH if priority_str.lower() == "high" else JobPriority.NORMAL
        job = Job(printer_id, commands, priority)
        with self.lock:
            self.db.create_job(job.job_id, printer_id, commands, priority.value)
        log(f"Created job {job.job_id} for printer {printer_id} with priority {priority.name}")
        return job

    def get_job(self, job_id):
        with self.lock:
            row = self.db.get_job(job_id)
            return Job.from_db_row(row) if row else None

    def update_job_status(self, job_id, status, error=None, responses=None, retry_count=None, next_retry_at=None):
        with self.lock:
            self.db.update_job_status(job_id, status, error, responses, retry_count, next_retry_at)
            log(f"Updated job {job_id} status to {status.value if hasattr(status, 'value') else status}")

    def get_all_jobs(self):
        with self.lock:
            rows = self.db.get_all_jobs()
            return [Job.from_db_row(row).to_dict() for row in rows]

    def get_jobs_by_status(self, status):
        with self.lock:
            rows = self.db.get_jobs_by_status(status.value if hasattr(status, 'value') else status)
            return [Job.from_db_row(row).to_dict() for row in rows]

    def get_pending_jobs(self, printer_id=None, limit=10):
        with self.lock:
            rows = self.db.get_pending_jobs(printer_id, limit)
            return [Job.from_db_row(row) for row in rows]

    def get_metrics(self):
        with self.lock:
            return self.db.get_metrics()
