# app/models/__init__.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def init_app(app):
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    db.init_app(app)
    migrate.init_app(app, db)

# 👇 Importaciones para registrar los modelos
from .contract_abi import ContractABI  # noqa
from .job import AnalysisJob  # noqa
from .audit import ContractAudit       # noqa

# 👇 Exportaciones explícitas
__all__ = ["db", "migrate", "ContractABI", "AnalysisJob", "ContractAudit"]
