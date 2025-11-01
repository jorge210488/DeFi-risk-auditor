from flask import Flask
from flasgger import Swagger
from prometheus_flask_exporter import PrometheusMetrics
from flask_cors import CORS
import os

from .logging_setup import setup_logging
from .routes import task_routes, blockchain_routes, health, ai_routes, audit_routes
from .config import DevelopmentConfig, ProductionConfig, TestingConfig


def create_app(config_name: str = "development"):
    app = Flask(__name__)

    config_map = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig,
    }
    app.config.from_object(config_map.get(config_name.lower(), DevelopmentConfig))

    setup_logging(app)

    # 👇 CORS desde variable de entorno CORS_ORIGIN
    # - CORS_ORIGIN no seteada o '*'  -> permite todos los orígenes
    # - CORS_ORIGIN="https://app.example.com,https://admin.example.com" -> sólo esos
    cors_origin = os.getenv("CORS_ORIGINS", "*").strip()
    cors_common_kwargs = dict(
        supports_credentials=False,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "Accept",
            "Origin",
            "User-Agent",
            "Cache-Control",
            "Pragma",
        ],
    )
    if cors_origin == "*" or cors_origin == "":
        CORS(app, resources={r"/*": {"origins": "*"}}, **cors_common_kwargs)
    else:
        origins_list = [o.strip() for o in cors_origin.split(",") if o.strip()]
        CORS(app, resources={r"/*": {"origins": origins_list}}, **cors_common_kwargs)
    # Ejemplo (comentado) para un único origen específico:
    # CORS(app, resources={r"/*": {"origins": ["https://app.example.com"]}}, **cors_common_kwargs)

    # 👇 Importar models aquí (ya con app creada y PYTHONPATH listo)
    from .models import init_app as init_models
    init_models(app)

    # Swagger
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "DeFi Risk Auditor API",
            "description": "API para llamadas a contratos, IA y auditorías.",
            "version": "1.0.0",
        },
        "basePath": "/",
        "schemes": ["https"],
    }
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec_1",
                "route": "/apispec_1.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/apidocs/",
    }
    Swagger(app, template=swagger_template, config=swagger_config)

    # Blueprints
    app.register_blueprint(task_routes.bp)
    app.register_blueprint(blockchain_routes.bp, url_prefix="/api/blockchain")
    app.register_blueprint(health.bp)
    app.register_blueprint(ai_routes.bp)
    app.register_blueprint(audit_routes.bp, url_prefix="/api/audit")

    # Métricas
    metrics = PrometheusMetrics(app, path="/metrics")
    metrics.info("app_info", "DeFi Risk Auditor service", version="1.0.0")

    return app
