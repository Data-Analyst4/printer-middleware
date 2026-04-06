import uuid
import json
from datetime import datetime
from enum import Enum

class JobStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

class JobPriority(Enum):
    HIGH = 1
    NORMAL = 2

class Job:
    def __init__(self, printer_id, commands, priority=JobPriority.NORMAL, job_id=None):
        self.job_id = job_id or str(uuid.uuid4())
        self.printer_id = printer_id
        self.status = JobStatus.QUEUED
        self.priority = priority
        self.commands = commands
        self.responses = []
        self.error = None
        self.retry_count = 0
        self.max_retries = 5
        self.next_retry_at = None
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

    @classmethod
    def from_db_row(cls, row):
        job = cls(
            printer_id=row['printer_id'],
            commands=json.loads(row['commands']),
            priority=JobPriority(row['priority']),
            job_id=row['job_id']
        )
        job.status = JobStatus(row['status'])
        job.responses = json.loads(row['responses'] or '[]')
        job.error = row['error']
        job.retry_count = row['retry_count']
        job.max_retries = row['max_retries']
        job.next_retry_at = row['next_retry_at']
        job.created_at = row['created_at']
        job.updated_at = row['updated_at']
        return job

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "printer_id": self.printer_id,
            "status": self.status.value,
            "priority": self.priority.name.lower(),
            "commands": self.commands,
            "responses": self.responses,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_retry_at": self.next_retry_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    def update_status(self, status, error=None):
        self.status = status
        self.updated_at = datetime.now().isoformat()
        if error:
            self.error = error

    def should_retry(self):
        return self.retry_count < self.max_retries

    def increment_retry(self):
        self.retry_count += 1
        # Exponential backoff: 5s, 30s, 2min, 10min
        delays = [5, 30, 120, 600]
        delay = delays[min(self.retry_count - 1, len(delays) - 1)]
        self.next_retry_at = (datetime.now().timestamp() + delay)
        self.status = JobStatus.RETRYING