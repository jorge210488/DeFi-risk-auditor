# app/tasks/ai_tasks.py
from datetime import datetime
from celery import shared_task
from app.models import db, AnalysisJob
from app.services.ai_service import risk_score

@shared_task(name="ai.predict")
def ai_predict_task(job_id: int):
    job = AnalysisJob.query.get(job_id)
    if not job:
        return {"error": "job no encontrado", "job_id": job_id}
    try:
        res = risk_score(job.params or {})
        job.status = "done"
        job.result = res
        job.updated_at = datetime.utcnow()
        db.session.commit()
        return res
    except Exception as e:
        job.status = "error"
        job.result = {"error": str(e)}
        job.updated_at = datetime.utcnow()
        db.session.commit()
        raise
