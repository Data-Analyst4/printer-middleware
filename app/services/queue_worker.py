from app.models.job import JobStatus
from app.utils.logger import log
import time

def printer_worker(printer, job_manager):
    """Enhanced worker with persistent connection and robust error handling"""
    while True:
        try:
            # Get job from priority queue: (priority_number, counter, job)
            priority_num, counter, job = printer["queue"].get()

            # Update job status to processing
            job_manager.update_job_status(job.job_id, JobStatus.PROCESSING)
            log(f"Processing job {job.job_id} for printer {job.printer_id}")

            responses = []
            error = None

            try:
                # Send each command with retry logic
                for cmd in job.commands:
                    response = None
                    for attempt in range(3):  # 3 retry attempts
                        try:
                            response = printer["connection"].send_command(cmd)
                            if response:
                                responses.append(response)
                            log(f"Command sent successfully for job {job.job_id}, attempt {attempt + 1}")
                            break
                        except Exception as e:
                            log(f"Attempt {attempt + 1} failed for job {job.job_id}: {e}")
                            if attempt < 2:  # Wait before retry (except last attempt)
                                time.sleep(1)
                            else:
                                error = str(e)

                    if error:
                        break

                    time.sleep(0.3)  # Small delay between commands

                # Update final job status
                if error:
                    job_manager.update_job_status(job.job_id, JobStatus.FAILED, error)
                    log(f"Job {job.job_id} failed: {error}")
                else:
                    job_manager.update_job_status(job.job_id, JobStatus.COMPLETED)
                    log(f"Job {job.job_id} completed successfully")

                # Add responses to job
                for resp in responses:
                    job_manager.update_job_status(job.job_id, JobStatus.COMPLETED, response=resp)

            except Exception as e:
                error = str(e)
                job_manager.update_job_status(job.job_id, JobStatus.FAILED, error)
                log(f"Unexpected error processing job {job.job_id}: {error}")

        except Exception as e:
            log(f"Critical error in worker for printer {printer.get('printer_id', 'unknown')}: {e}")
        finally:
            printer["queue"].task_done()