import threading
import time
import json
from datetime import datetime
from app.models.job import JobStatus
from app.services.connection_manager import ConnectionManager
from app.utils.logger import log

class PrinterWorker:
    def __init__(self, printer_id, ip, port, job_manager, db_manager):
        self.printer_id = printer_id
        self.ip = ip
        self.port = port
        self.job_manager = job_manager
        self.db_manager = db_manager
        self.connection = ConnectionManager(printer_id, ip, port)
        self.running = True
        self.thread = threading.Thread(target=self._work_loop, daemon=True)
        self.thread.start()

    def _work_loop(self):
        log(f"Started worker for printer {self.printer_id}")
        while self.running:
            try:
                # Get pending jobs for this printer
                jobs = self.job_manager.get_pending_jobs(self.printer_id, limit=1)
                if not jobs:
                    time.sleep(1)  # No jobs, wait
                    continue

                job = jobs[0]
                log(f"Processing job {job.job_id} for printer {self.printer_id}")

                # Update job status to processing
                self.job_manager.update_job_status(job.job_id, JobStatus.PROCESSING)

                # Execute commands
                responses = []
                error = None

                for cmd in job.commands:
                    response = None
                    for attempt in range(3):  # 3 retry attempts per command
                        try:
                            response = self.connection.send_command(cmd)
                            responses.append(response)
                            log(f"Command sent successfully for job {job.job_id}, attempt {attempt + 1}")
                            break
                        except Exception as e:
                            log(f"Attempt {attempt + 1} failed for job {job.job_id}: {e}")
                            if attempt < 2:
                                time.sleep(1)
                            else:
                                error = str(e)

                    if error:
                        break

                    time.sleep(0.3)  # Small delay between commands

                # Update job final status
                if error:
                    if job.should_retry():
                        job.increment_retry()
                        self.job_manager.update_job_status(
                            job.job_id,
                            JobStatus.RETRYING,
                            error=error,
                            retry_count=job.retry_count,
                            next_retry_at=datetime.fromtimestamp(job.next_retry_at).isoformat()
                        )
                        log(f"Job {job.job_id} failed, scheduled for retry {job.retry_count}/{job.max_retries}")
                    else:
                        self.job_manager.update_job_status(job.job_id, JobStatus.FAILED, error=error)
                        log(f"Job {job.job_id} failed permanently: {error}")
                else:
                    self.job_manager.update_job_status(job.job_id, JobStatus.COMPLETED)
                    # Add responses to job
                    for resp in responses:
                        if resp:  # Only add non-None responses
                            self.job_manager.update_job_status(job.job_id, JobStatus.COMPLETED, response=resp)
                    log(f"Job {job.job_id} completed successfully")

                # Update printer last seen
                self.db_manager.update_printer_status(self.printer_id)

            except Exception as e:
                log(f"Critical error in worker for printer {self.printer_id}: {e}")
                time.sleep(5)  # Back off on critical errors

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=5)

class WorkerManager:
    def __init__(self, job_manager, db_manager):
        self.job_manager = job_manager
        self.db_manager = db_manager
        self.workers = {}  # printer_id -> list of workers
        self.lock = threading.Lock()

    def register_printer(self, printer_id, ip, port, worker_count=2):
        """Register a printer with multiple workers"""
        with self.lock:
            if printer_id in self.workers:
                # Update existing workers
                for worker in self.workers[printer_id]:
                    worker.ip = ip
                    worker.port = port
                    worker.connection.update_target(ip, port)
            else:
                # Create new workers
                self.workers[printer_id] = []
                for i in range(worker_count):
                    worker = PrinterWorker(
                        f"{printer_id}_{i}",
                        ip,
                        port,
                        self.job_manager,
                        self.db_manager
                    )
                    self.workers[printer_id].append(worker)

            # Register in database
            self.db_manager.register_printer(printer_id, ip, port)
            log(f"Registered printer {printer_id} with {worker_count} workers")

    def get_printer_status(self, printer_id):
        """Get status of all workers for a printer"""
        with self.lock:
            if printer_id not in self.workers:
                return {"status": "not_registered"}

            workers_status = []
            for worker in self.workers[printer_id]:
                workers_status.append({
                    "worker_id": worker.printer_id,
                    "connected": worker.connection.connected,
                    "running": worker.running
                })

            return {
                "printer_id": printer_id,
                "ip": self.workers[printer_id][0].ip if self.workers[printer_id] else None,
                "port": self.workers[printer_id][0].port if self.workers[printer_id] else None,
                "workers": workers_status,
                "worker_count": len(workers_status)
            }

    def get_all_printers_status(self):
        """Get status of all registered printers"""
        with self.lock:
            result = {}
            for printer_id in self.workers:
                result[printer_id] = self.get_printer_status(printer_id)
            return result

    def stop_all(self):
        """Stop all workers"""
        with self.lock:
            for printer_id, workers in self.workers.items():
                for worker in workers:
                    worker.stop()
            self.workers.clear()