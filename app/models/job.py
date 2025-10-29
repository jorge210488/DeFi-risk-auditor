from datetime import datetime
from app.models import db

class AnalysisJob(db.Model):
    __tablename__ = "analysis_jobs"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(50), index=True, unique=True, nullable=True)
    status = db.Column(db.String(20), default="queued", index=True)
    params = db.Column(db.JSON, nullable=True)
    result = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
