# app/tasks/celery_app.py
import os
from celery import Celery

def make_celery() -> Celery:
    """
    Crea una instancia de Celery con defaults sensatos.
    Usa result_backend (clave no deprecada) y deja todo listo
    por si todavía no existe el contexto de Flask.
    """
    celery = Celery("defi_risk_auditor")

    # Defaults desde variables de entorno (antes de tener Flask)
    celery.conf.broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    # Usa la clave NO deprecada (result_backend). Si no la pasas, cae al broker.
    celery.conf.result_backend = os.getenv(
        "CELERY_RESULT_BACKEND",
        os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    )

    # Ajustes razonables
    celery.conf.update(
        task_ignore_result=False,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone=os.getenv("TZ", "UTC"),
        enable_utc=True,
    )
    return celery

celery = make_celery()

def _init_celery_with_flask():
    """
    Enlaza Celery con Flask:
      - toma la config de Flask si existe (mapea CELERY_* -> broker_url/result_backend)
      - envuelve las tasks con app.app_context()
      - importa el módulo de tareas para registrarlas
    """
    # Import diferido para evitar circular imports
    from app import create_app

    config_name = os.getenv("FLASK_ENV", "development")
    app = create_app(config_name)

    # Mapear config de Flask a claves modernas de Celery
    broker = app.config.get("CELERY_BROKER_URL") or app.config.get("broker_url")
    backend = (
        app.config.get("CELERY_RESULT_BACKEND")
        or app.config.get("result_backend")
        or app.config.get("CELERY_BROKER_URL")  # fallback común en Redis
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

    # Registrar las tareas (importa el módulo que define @celery.task)
    with app.app_context():
        from app.tasks import background_tasks  # noqa: F401

    return app

# Inicializa una vez al importar
_flask_app = _init_celery_with_flask()
