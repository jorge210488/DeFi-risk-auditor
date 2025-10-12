# app/__init__.py
from flask import Flask
from app.routes import task_routes, blockchain_routes  # Blueprints existentes
from app.models import init_app as init_models         # Registra DB + Migrate
from app.routes import health as health_routes         # /healthz si lo tienes

def create_app(config_name: str = "development"):
    app = Flask(__name__)

    # Cargar configuración según entorno (DevelopmentConfig / ProductionConfig)
    app.config.from_object(f"app.config.{config_name.capitalize()}Config")

    # Inicializar SQLAlchemy + Flask-Migrate (habilita `flask db ...`)
    init_models(app)

    # Registrar Blueprints
    app.register_blueprint(task_routes.bp)                           # "/", "/procesar"
    app.register_blueprint(blockchain_routes.bp, url_prefix="/api/blockchain")
    app.register_blueprint(health_routes.bp)                         # "/healthz"

    return app
