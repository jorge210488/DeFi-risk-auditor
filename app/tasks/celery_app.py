# app/tasks/celery_app.py

import os
from celery import Celery

def make_celery() -> Celery:
    """
    Create a base Celery instance with sensible default configuration.
    Uses the modern `result_backend` key (not deprecated).
    """
    celery_app = Celery("defi_risk_auditor")

    # Default broker/result from environment, or fallback to Redis on localhost.
    celery_app.conf.broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    celery_app.conf.result_backend = os.getenv(
        "CELERY_RESULT_BACKEND",
        os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    )

    # Recommended Celery configuration
    celery_app.conf.update(
        task_ignore_result=False,   # allow task results (can be True if results mostly unused)
        task_serializer="json",
        accept_content=["json"],    # accept only JSON (safer serialization)
        result_serializer="json",
        timezone=os.getenv("TZ", "UTC"),
        enable_utc=True,
    )
    return celery_app

# Initialize the Celery app
celery = make_celery()

def _init_celery_with_flask():
    """
    Bind Celery with the Flask app:
      - Load Flask app config into Celery (maps CELERY_* keys to broker/result)
      - Wrap tasks to run inside the Flask app context
      - Import task modules to register them with Celery
    """
    # Deferred import to avoid circular imports
    from app import create_app

    config_name = os.getenv("FLASK_ENV", "development")
    flask_app = create_app(config_name)  # Create the Flask app instance

    # Map Flask app config to Celery config, if present
    broker = flask_app.config.get("CELERY_BROKER_URL") or flask_app.config.get("broker_url")
    backend = (
        flask_app.config.get("CELERY_RESULT_BACKEND")
        or flask_app.config.get("result_backend")
        or flask_app.config.get("CELERY_BROKER_URL")  # common fallback to broker if separate backend not set
    )
    if broker:
        celery.conf.broker_url = broker
    if backend:
        celery.conf.result_backend = backend

    # Define a Task base that ensures task execution is within Flask app context
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        """Make Celery tasks execute within the Flask application context."""
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask

    # Set this Celery app as the default app for tasks (needed for @shared_task):contentReference[oaicite:1]{index=1}
    celery.set_default()

    # Import tasks modules to register task definitions with Celery
    with flask_app.app_context():
        # Import all task modules so their @shared_task decorators register with our Celery app
        from app.tasks import background_tasks  # noqa: F401
        from app.tasks import blockchain_tasks  # noqa: F401
        try:
            from app.tasks import ai_tasks  # noqa: F401  # (optional, Stage 3: AI background tasks)
        except ImportError:
            pass
        try:
            from app.tasks import audit_tasks  # noqa: F401  # (optional, Stage 4: on-chain audit tasks)
        except ImportError:
            pass

    return flask_app

# Initialize Flask app and register tasks at import time
_flask_app = _init_celery_with_flask()
