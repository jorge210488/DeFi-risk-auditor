from flask import Blueprint, jsonify, request
from app.models import db
from app.models.job import AnalysisJob

bp = Blueprint("tasks", __name__)

@bp.route("/", methods=["GET"])
def index():
    """
    Root
    ---
    tags:
      - Tasks
    responses:
      200:
        description: OK
    """
    return jsonify({"message": "Backend OK. Usa /procesar y /jobs/<id>"}), 200

@bp.route("/procesar", methods=["GET", "POST"])
def procesar():
    """
    Encola una tarea de ejemplo
    ---
    tags:
      - Tasks
    consumes:
      - application/json
    parameters:
      - in: body
        name: params
        required: false
        schema:
          type: object
    responses:
      202:
        description: Aceptado
    """
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
    """
    Obtener estado de un job
    ---
    tags:
      - Tasks
    parameters:
      - in: path
        name: job_id
        required: true
        type: integer
    responses:
      200: {description: OK}
      404: {description: No encontrado}
    """
    job = db.session.get(AnalysisJob, job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify({
        "job_id": job.id,
        "task_id": job.task_id,
        "status": job.status,
        "result": job.result
    }), 200
