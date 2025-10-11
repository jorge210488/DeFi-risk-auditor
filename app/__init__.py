# app/__init__.py
from flask import Flask
from app.routes import task_routes, blockchain_routes  # Blueprints existentes
from app.models import init_app as init_models         # ⬅️ IMPORTANTE: registrar DB/Migrate
from app.routes import health as health_routes

def create_app(config_name="development"):
    app = Flask(__name__)
    # Cargar configuración según entorno
    app.config.from_object(f"app.config.{config_name.capitalize()}Config")

    # Registrar SQLAlchemy + Flask-Migrate
    init_models(app)  # ⬅️ ESTO habilita los comandos `flask db ...`

    # Registrar Blueprints
    app.register_blueprint(task_routes.bp)
    app.register_blueprint(blockchain_routes.bp, url_prefix="/api/blockchain")
    app.register_blueprint(health_routes.bp)

    return app
