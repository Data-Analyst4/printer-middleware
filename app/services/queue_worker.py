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
                for idx, cmd in enumerate(job.commands):
                    response = None
                    for attempt in range(3):  # 3 retry attempts
                        try:
                            response = printer["connection"].send_command(cmd)
                            attempt_record = {
                                "index": idx,
                                "attempt": attempt + 1,
                                "command": cmd,
                                "ok": response.get("ok", False),
                                "reason": response.get("reason"),
                                "response_command": response.get("response_command"),
                                "response_status": response.get("response_status"),
                                "protocol_error_code": response.get("protocol_error_code"),
                                "protocol_error_description": response.get("protocol_error_description"),
                                "error_type": response.get("error_type"),
                                "raw_response": response.get("raw_response"),
                                "response": response.get("response"),
                                "details": response
                            }
                            responses.append(attempt_record)

                            if response.get("ok", False):
                                log(
                                    f"Command acknowledged for job {job.job_id}, "
                                    f"attempt {attempt + 1}, "
                                    f"printer_response={response.get('response_command') or 'n/a'}"
                                )
                                break

                            reason = response.get("reason") or "Unsuccessful printer response"
                            log(
                                f"Attempt {attempt + 1} received unsuccessful response for job {job.job_id}: {reason}"
                            )

                            if attempt < 2:
                                time.sleep(1)
                            else:
                                error = reason
                        except Exception as e:
                            responses.append({
                                "index": idx,
                                "attempt": attempt + 1,
                                "command": cmd,
                                "ok": False,
                                "reason": str(e),
                                "error_type": "transport_exception",
                                "raw_response": None,
                                "response": None
                            })
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
                    job_manager.update_job_status(job.job_id, JobStatus.FAILED, error=error, responses=responses)
                    log(f"Job {job.job_id} failed: {error}")
                else:
                    job_manager.update_job_status(job.job_id, JobStatus.COMPLETED, responses=responses)
                    log(f"Job {job.job_id} completed successfully")

            except Exception as e:
                error = str(e)
                job_manager.update_job_status(job.job_id, JobStatus.FAILED, error=error, responses=responses)
                log(f"Unexpected error processing job {job.job_id}: {error}")

        except Exception as e:
            log(f"Critical error in worker for printer {printer.get('printer_id', 'unknown')}: {e}")
        finally:
            printer["queue"].task_done()
