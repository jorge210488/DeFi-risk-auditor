# app/routes/task_routes.py
from flask import Blueprint, jsonify, request
from app.models import db
from app.models.job import AnalysisJob

bp = Blueprint("tasks", __name__)

@bp.route("/", methods=["GET"])
def index():
    return jsonify({"message": "Backend OK. Usa /procesar y /jobs/<id>"}), 200

@bp.route("/procesar", methods=["GET", "POST"])
def procesar():
    # import diferido para evitar circular import
    from app.tasks.background_tasks import background_task

    params = request.get_json(silent=True) or {}
    job = AnalysisJob(status="queued", params=params)
    db.session.add(job)
    db.session.commit()

    async_res = background_task.delay(job.id)
    job.task_id = async_res.id
    db.session.commit()

    return jsonify({"job_id": job.id, "task_id": job.task_id, "status": job.status}), 202

@bp.route("/jobs/<int:job_id>", methods=["GET"])
def job_status(job_id: int):
    job = db.session.get(AnalysisJob, job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify({
        "job_id": job.id,
        "task_id": job.task_id,
        "status": job.status,
        "result": job.result
    }), 200
