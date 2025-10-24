from flask import Flask
from app.routes import task_routes, blockchain_routes, health, ai_routes, audit_routes
from app.models import init_app as init_models

def create_app(config_name: str = "development"):
    app = Flask(__name__)

    # Cargar configuración
    app.config.from_object(f"app.config.{config_name.capitalize()}Config")

    # Inicializar DB
    init_models(app)

    # Registrar blueprints
    app.register_blueprint(task_routes.bp)
    app.register_blueprint(blockchain_routes.bp, url_prefix="/api/blockchain")
    app.register_blueprint(health.bp)
    app.register_blueprint(ai_routes.bp)  # ✅ ya tiene su url_prefix en el blueprint
    app.register_blueprint(audit_routes.bp, url_prefix="/api/audit")

    return app
