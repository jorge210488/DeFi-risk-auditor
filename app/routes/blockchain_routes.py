# app/routes/blockchain_routes.py
from flask import Blueprint, jsonify

bp = Blueprint("blockchain", __name__)

@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200
