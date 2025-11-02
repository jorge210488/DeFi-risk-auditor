#!/usr/bin/env bash
set -e

echo "==== DEBUG PATHS ===="
echo "PWD: $(pwd)"
echo "PYTHONPATH: $PYTHONPATH"
python - <<'PY'
import sys, importlib
print("sys.path:", sys.path)
try:
    import app
    print("app.__file__ =", getattr(app, "__file__", None))
    m = importlib.import_module("app.models")
    print("app.models loaded from:", getattr(m, "__file__", None))
except Exception as e:
    print("DEBUG IMPORT ERROR:", repr(e))
PY
echo "======================"

echo "Ejecutando migraciones (si existen)..."
python -m flask --app wsgi.py db upgrade || echo "Migraciones no ejecutadas (comando db no disponible o sin cambios)."

# --- Celery en el mismo contenedor del web (opcional) ---
# Actívalo con RUN_CELERY_IN_WEB=1 en variables de entorno del servicio web.
# Pool "solo" y concurrency 1 para ahorrar RAM en el tier gratis.
if [ "${RUN_CELERY_IN_WEB}" = "1" ] || [ "${RUN_CELERY_IN_WEB}" = "true" ]; then
  echo "[entrypoint] Starting Celery worker in background..."
  celery -A app.tasks.celery_app.celery worker \
    --loglevel="${CELERY_LOGLEVEL:-INFO}" \
    --concurrency="${CELERY_CONCURRENCY:-1}" \
    --pool=solo &
fi

echo "Iniciando aplicación..."
exec python wsgi.py
