# app/tasks/background_tasks.py

import time
from datetime import datetime
from celery import shared_task
from app.models import db
from app.models.job import AnalysisJob

@shared_task(name="app.tasks.background_tasks.background_task")
def background_task(job_id: int):
    """
    Example background task that marks a job as running, simulates work, and finishes the job.
    """
    # Retrieve the job from the database
    job = db.session.get(AnalysisJob, job_id)
    if not job:
        # If no job is found, return an error result (job might have been deleted or invalid ID)
        return {"error": f"AnalysisJob id {job_id} not found"}

    # Mark job as running and commit to database
    job.status = "running"
    job.updated_at = datetime.utcnow()
    db.session.commit()

    # --- Simulated long-running work ---
    time.sleep(2)  # simulate a delay for the task
    result_data = {"message": "Tarea completada correctamente desde Celery"}
    # ------------------------------------

    # Mark job as done with result and commit
    job.result = result_data
    job.status = "done"
    job.updated_at = datetime.utcnow()
    db.session.commit()

    return result_data
