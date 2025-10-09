from celery import Celery
import os

# Usa la variable de entorno definida en docker-compose.yml
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

app = Celery(
    "tasks",
    broker=broker_url,
    backend=broker_url
)

@app.task
def background_task():
    print("✅ Ejecutando tarea en segundo plano...")
    return "Tarea completada correctamente desde Celery"
