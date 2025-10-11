# app/routes/health.py
from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)

@bp.get("/healthz")
def healthz():
    return jsonify(ok=True), 200
