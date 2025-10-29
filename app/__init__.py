from flask import Flask
from flasgger import Swagger
from prometheus_flask_exporter import PrometheusMetrics  # Importar PrometheusMetrics

from app.logging_setup import setup_logging
from app.models import init_app as init_models
from app.routes import task_routes, blockchain_routes, health, ai_routes, audit_routes

def create_app(config_name: str = "development"):
    app = Flask(__name__)
    app.config.from_object(f"app.config.{config_name.capitalize()}Config")

    setup_logging(app)
    init_models(app)

    # Configuración de Swagger (documentación interactiva en /apidocs/)
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "DeFi Risk Auditor API",
            "description": "API para llamadas a contratos, IA y auditorías.",
            "version": "1.0.0",
        },
        "basePath": "/",
        "schemes": ["http"],
    }
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec_1",
                "route": "/apispec_1.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/apidocs/",
    }
    Swagger(app, template=swagger_template, config=swagger_config)

    # Registro de Blueprints (rutas de la aplicación)
    app.register_blueprint(task_routes.bp)
    app.register_blueprint(blockchain_routes.bp, url_prefix="/api/blockchain")
    app.register_blueprint(health.bp)
    app.register_blueprint(ai_routes.bp)
    app.register_blueprint(audit_routes.bp, url_prefix="/api/audit")

    # Métricas de Prometheus en /metrics
    metrics = PrometheusMetrics(app, path="/metrics")
    metrics.info("app_info", "DeFi Risk Auditor service", version="1.0.0")

    return app
