import os
import logging
from celery import Celery

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def make_celery() -> Celery:
    """
    Crea una instancia base de Celery con configuración por defecto.
    Incluye verificación de conexión y logs de diagnóstico.
    """
    celery_app = Celery("defi_risk_auditor")

    broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    result_backend = os.getenv("CELERY_RESULT_BACKEND", broker_url)

    celery_app.conf.update(
        broker_url=broker_url,
        result_backend=result_backend,
        task_ignore_result=False,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone=os.getenv("TZ", "UTC"),
        enable_utc=True,
    )

    # Diagnóstico de conexión
    try:
        conn = celery_app.connection()
        conn.ensure_connection(max_retries=1)
        logger.info(f"✅ Celery conectado correctamente a broker: {broker_url}")
    except Exception as e:
        logger.error(f"❌ Error conectando a Celery broker ({broker_url}): {e}")

    try:
        backend = celery_app.backend
        if backend:
            backend.ensure_not_eager()
            logger.info(f"✅ Backend de resultados configurado: {result_backend}")
    except Exception as e:
        logger.error(f"❌ Error en backend de resultados ({result_backend}): {e}")

    return celery_app

celery = make_celery()

def _init_celery_with_flask():
    """Inicializa Celery dentro del contexto Flask."""
    from app import create_app
    config_name = os.getenv("FLASK_ENV", "development")
    flask_app = create_app(config_name)

    broker = flask_app.config.get("CELERY_BROKER_URL") or flask_app.config.get("broker_url")
    backend = (
        flask_app.config.get("CELERY_RESULT_BACKEND")
        or flask_app.config.get("result_backend")
        or flask_app.config.get("CELERY_BROKER_URL")
    )

    if broker:
        celery.conf.broker_url = broker
    if backend:
        celery.conf.result_backend = backend

    TaskBase = celery.Task

    class ContextTask(TaskBase):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    celery.set_default()

    with flask_app.app_context():
        from app.tasks import background_tasks, blockchain_tasks
        try:
            from app.tasks import ai_tasks
        except ImportError:
            pass
        try:
            from app.tasks import audit_tasks
        except ImportError:
            pass

    return flask_app

_flask_app = _init_celery_with_flask()
