#!/bin/bash
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

echo "Iniciando aplicación..."
exec python wsgi.py
