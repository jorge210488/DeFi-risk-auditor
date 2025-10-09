from flask import Flask
from tasks import background_task  # importamos la tarea que definiremos en tasks.py

app = Flask(__name__)

@app.route("/")
def index():
    return "¡Aplicación Flask funcionando! Visita /procesar para ejecutar la tarea.", 200

@app.route("/procesar")
def procesar():
    # Encolar una tarea Celery de forma asíncrona
    result = background_task.delay()  
    # .delay() lanza la tarea en segundo plano inmediatamente:contentReference[oaicite:18]{index=18} 
    return f"Tarea encolada (ID: {result.id}). La estamos procesando en segundo plano...", 202

# Punto de entrada para ejecutar la app en desarrollo
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

