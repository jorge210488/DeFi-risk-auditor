# app/tasks/background_tasks.py
import time
from app.tasks.celery_app import celery
from app.models import db
from app.models.job import AnalysisJob

@celery.task(name="app.tasks.background_tasks.background_task")
def background_task(job_id: int):
    # Ya estamos dentro de app_context gracias a ContextTask en celery_app.py
    job = db.session.get(AnalysisJob, job_id)
    if job:
        job.status = "running"
        db.session.commit()

    # --- trabajo simulado ---
    time.sleep(2)
    result = {"message": "Tarea completada correctamente desde Celery"}
    # ------------------------

    if job:
        job.result = result
        job.status = "done"
        db.session.commit()

    return result
