# app/tasks/celery_app.py
import os
from celery import Celery

def make_celery() -> Celery:
    """
    Crea una instancia base de Celery con valores sensatos.
    Usa la clave moderna `result_backend` (no deprecada).
    """
    c = Celery("defi_risk_auditor")

    # Defaults desde variables de entorno (antes de tener Flask)
    c.conf.broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    c.conf.result_backend = os.getenv(
        "CELERY_RESULT_BACKEND",
        os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    )

    # Ajustes recomendados
    c.conf.update(
        task_ignore_result=False,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone=os.getenv("TZ", "UTC"),
        enable_utc=True,
    )
    return c

celery = make_celery()


def _init_celery_with_flask():
    """
    Enlaza Celery con Flask:
      - toma config de Flask (mapea CELERY_* -> broker_url/result_backend)
      - envuelve tasks con app.app_context()
      - importa módulos de tasks para registrarlas
    """
    # Import diferido para evitar import circular
    from app import create_app

    config_name = os.getenv("FLASK_ENV", "development")
    app = create_app(config_name)

    # Mapear config de Flask a claves de Celery (por si están en config)
    broker = app.config.get("CELERY_BROKER_URL") or app.config.get("broker_url")
    backend = (
        app.config.get("CELERY_RESULT_BACKEND")
        or app.config.get("result_backend")
        or app.config.get("CELERY_BROKER_URL")  # fallback típico con Redis
    )
    if broker:
        celery.conf.broker_url = broker
    if backend:
        celery.conf.result_backend = backend

    # Ejecutar cada task dentro del app_context de Flask
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery.Task = ContextTask

    # Registrar las tareas (importa los módulos que definen @shared_task)
    with app.app_context():
        from app.tasks import background_tasks  # noqa: F401

        # Mantener todos los módulos de tasks que ya tienes en el proyecto:
        try:
            from app.tasks import blockchain_tasks  # noqa: F401
        except Exception:
            pass
        try:
            from app.tasks import ai_tasks  # noqa: F401  <-- Etapa 3 (IA en background)
        except Exception:
            pass
        try:
            from app.tasks import audit_tasks  # noqa: F401  <-- Etapa 4 (auditoría on-chain + IA)
        except Exception:
            pass

    return app


# Inicializa una vez al importar este módulo
_flask_app = _init_celery_with_flask()
