from flask import Blueprint, jsonify, request
from app.services.ai_service import risk_score

# Agregamos el prefijo aquí
bp = Blueprint("ai", __name__, url_prefix="/api/ai")

@bp.route("/predict", methods=["POST"])
def predict():
    """
    Body JSON (ejemplo):
    {
      "feature1": 0.7,
      "feature2": -0.1
    }
    """
    payload = request.get_json(silent=True) or {}
    try:
        out = risk_score(payload)
        return jsonify({"ok": True, **out}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
