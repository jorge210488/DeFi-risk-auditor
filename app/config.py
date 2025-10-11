# app/config.py
import os

class BaseConfig:
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

    # --- DB ---
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg2://app_user:app_pass@db:5432/app_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False

class DevelopmentConfig(BaseConfig):
    DEBUG = True
    ENV = "development"

class ProductionConfig(BaseConfig):
    DEBUG = False
    ENV = "production"
    # Aquí luego podés añadir logging seguro, CORS, etc.
