#!/bin/bash
set -e

echo "Ejecutando migraciones (si existen)..."
python -m flask --app wsgi.py db upgrade || echo "Migraciones no ejecutadas (comando db no disponible o sin cambios)."

echo "Iniciando aplicación..."
exec python wsgi.py
