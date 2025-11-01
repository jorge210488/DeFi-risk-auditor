# app/routes/audit_routes.py
from flask import Blueprint, jsonify, request
from app.models import db, AnalysisJob
from app.models.audit import ContractAudit

bp = Blueprint("audit", __name__)  # el prefijo se aplica al registrar en app/__init__.py

# --- Helpers locales ---

def _as_bool(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")

def _iso(dt):
    return dt.replace(microsecond=0).isoformat() + "Z" if dt else None


@bp.post("/start")
def start():
    """
    Auditoría: iniciar
    ---
    tags:
      - Audit
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - address
          properties:
            address:
              type: string
              description: Dirección del contrato a auditar.
              default: "0x3245166A4399A34A76cc9254BC13Aae3dA07e27b"
              example: "0x3245166A4399A34A76cc9254BC13Aae3dA07e27b"
            network:
              type: string
              description: Red a utilizar.
              default: "sepolia"
              example: "sepolia"
            force_refresh:
              type: boolean
              description: Forzar re-descarga de la ABI desde Etherscan.
              default: false
              example: false
          example:
            address: "0x3245166A4399A34A76cc9254BC13Aae3dA07e27b"
            network: "sepolia"
            force_refresh: false
    responses:
      202:
        description: Aceptado (job encolado)
      400:
        description: Faltan campos
      501:
        description: Task no disponible
    """
    data = request.get_json(silent=True) or {}
    address = (data.get("address") or data.get("contract_address") or "").strip()
    network = (data.get("network") or "sepolia").strip().lower()
    force_refresh = _as_bool(data.get("force_refresh", False))

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

    # Producción: 4 args; Tests (monkeypatch): puede aceptar solo 3 -> fallback
    try:
        async_res = run_audit.delay(job.id, address, network, force_refresh)
    except TypeError:
        async_res = run_audit.delay(job.id, address, network)

    job.task_id = async_res.id
    db.session.commit()

    return jsonify({"ok": True, "job_id": job.id, "task_id": async_res.id, "status": "queued"}), 202


@bp.get("/status/<int:job_id>")
def status(job_id: int):
    """
    Auditoría: estado de AnalysisJob
    ---
    tags:
      - Audit
    parameters:
      - in: path
        name: job_id
        required: true
        type: integer
        example: 1
    responses:
      200:
        description: OK
      404:
        description: No encontrado
    """
    job = AnalysisJob.query.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job no encontrado"}), 404

    return jsonify({
        "ok": True,
        "job_id": job.id,
        "status": job.status,
        "task_id": job.task_id,
        "result": job.result,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
    }), 200


@bp.get("/<int:audit_id>")
def get_audit(audit_id: int):
    """
    Auditoría: obtener detalle
    ---
    tags:
      - Audit
    parameters:
      - in: path
        name: audit_id
        required: true
        type: integer
        example: 1
    responses:
      200:
        description: OK
      404:
        description: No encontrada
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
            "started_at": _iso(audit.started_at),
            "finished_at": _iso(audit.finished_at),
        }
    }), 200


@bp.get("/")
def list_audits():
    """
    Auditoría: listar últimas 50 (filtrable por ?address=0x...)
    ---
    tags:
      - Audit
    parameters:
      - in: query
        name: address
        required: false
        type: string
        description: Filtra por dirección exacta (case-insensitive).
        example: "0x3245166A4399A34A76cc9254BC13Aae3dA07e27b"
    responses:
      200:
        description: OK
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
                "started_at": _iso(a.started_at),
                "finished_at": _iso(a.finished_at),
            } for a in audits
        ]
    }), 200
