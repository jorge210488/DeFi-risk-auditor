# app/routes/audit_routes.py
from flask import Blueprint, jsonify, request
from app.models import db, AnalysisJob
from app.models.audit import ContractAudit

bp = Blueprint("audit", __name__)  # el prefijo se pone en app/__init__.py

@bp.post("/start")
def start():
    """
    Inicia una auditoría
    Body JSON:
      {
        "address": "0x...",
        "network": "sepolia",         # opcional
        "force_refresh": false        # opcional, fuerza refresco ABI desde Etherscan
      }
    """
    data = request.get_json(silent=True) or {}
    address = data.get("address") or data.get("contract_address")
    network = data.get("network", "sepolia")
    force_refresh = bool(data.get("force_refresh", False))

    if not address:
        return jsonify({"ok": False, "error": "Falta 'address'"}), 400

    # Import diferido de la task
    try:
        from app.tasks.audit_tasks import run_audit
    except Exception:
        return jsonify({"ok": False, "error": "Task 'audit.run' no disponible"}), 501

    # Crear job y encolar
    job = AnalysisJob(
        status="queued",
        params={"address": address, "network": network, "force_refresh": force_refresh},
    )
    db.session.add(job)
    db.session.commit()

    async_res = run_audit.delay(job.id, address, network, force_refresh)
    job.task_id = async_res.id
    db.session.commit()

    return jsonify({"ok": True, "job_id": job.id, "task_id": async_res.id, "status": "queued"}), 202


@bp.get("/status/<int:job_id>")
def status(job_id: int):
    """
    Devuelve el estado del AnalysisJob (queued|running|done|error) y el result (si lo hay)
    """
    job = AnalysisJob.query.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job no encontrado"}), 404

    return jsonify({
        "ok": True,
        "job_id": job.id,
        "status": job.status,
        "task_id": job.task_id,
        "result": job.result
    }), 200


@bp.get("/<int:audit_id>")
def get_audit(audit_id: int):
    """
    Devuelve el detalle de un ContractAudit
    """
    audit = ContractAudit.query.get(audit_id)
    if not audit:
        return jsonify({"ok": False, "error": "audit no encontrada"}), 404

    return jsonify({
        "ok": True,
        "audit": {
            "id": audit.id,
            "address": audit.address,
            "network": audit.network,
            "status": audit.status,
            "ai_score": audit.ai_score,
            "risk_level": audit.risk_level,
            "summary": audit.summary,
            "features": audit.features,
            "details": audit.details,
            "started_at": audit.started_at.isoformat() if audit.started_at else None,
            "finished_at": audit.finished_at.isoformat() if audit.finished_at else None,
        }
    }), 200


@bp.get("/")
def list_audits():
    """
    Lista últimas 50 auditorías (filtrable por address)
    GET /api/audit?address=0x...
    """
    address = request.args.get("address")
    q = ContractAudit.query
    if address:
        q = q.filter(ContractAudit.address == address.lower())
    audits = q.order_by(ContractAudit.id.desc()).limit(50).all()

    return jsonify({
        "ok": True,
        "items": [
            {
                "id": a.id,
                "address": a.address,
                "network": a.network,
                "status": a.status,
                "ai_score": a.ai_score,
                "risk_level": a.risk_level,
                "summary": a.summary,
                "started_at": a.started_at.isoformat() if a.started_at else None,
                "finished_at": a.finished_at.isoformat() if a.finished_at else None,
            } for a in audits
        ]
    }), 200
