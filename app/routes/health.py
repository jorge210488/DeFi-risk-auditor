from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)

@bp.get("/healthz")
def healthz():
    """
    Healthcheck
    ---
    tags:
      - Health
    responses:
      200:
        description: OK
    """
    return jsonify({"ok": True}), 200
