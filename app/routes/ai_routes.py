from flask import Blueprint, jsonify, request
from app.services.ai_service import risk_score

# Prefijo aquí
bp = Blueprint("ai", __name__, url_prefix="/api/ai")

@bp.route("/predict", methods=["POST"])
def predict():
    """
    IA: Score de riesgo (demo)
    ---
    tags:
      - AI
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: false
        schema:
          type: object
          properties:
            feature1:
              type: number
              example: 0.3
            feature2:
              type: number
              example: -0.4
    responses:
      200:
        description: OK
      400:
        description: Error en entrada
    """
    payload = request.get_json(silent=True) or {}
    try:
        out = risk_score(payload)
        return jsonify({"ok": True, **out}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
