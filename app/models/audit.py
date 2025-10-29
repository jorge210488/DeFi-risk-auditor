# app/models/audit.py
from datetime import datetime
from app.models import db
from app.models.types import JSONBCompat  # 👈 importamos el tipo compatible

class ContractAudit(db.Model):
    __tablename__ = "contract_audits"

    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(42), index=True, nullable=False)
    network = db.Column(db.String(32), index=True, nullable=False, default="sepolia")

    status = db.Column(db.String(20), nullable=False, default="queued")  # queued|running|done|error
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    # Resultado principal
    ai_score = db.Column(db.Float, nullable=True)            # 0..1
    risk_level = db.Column(db.String(20), nullable=True)     # low|medium|high
    summary = db.Column(JSONBCompat(), nullable=True)        # dict corto (name, symbol, etc.)
    features = db.Column(JSONBCompat(), nullable=True)       # dict de features para IA
    details = db.Column(JSONBCompat(), nullable=True)        # info extra (flags, llamadas, etc.)
