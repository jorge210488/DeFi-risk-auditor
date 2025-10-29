FROM python:3.10-slim
WORKDIR /app
ENV PYTHONPATH=/app

# Crear usuario no-root
RUN useradd -m -u 1000 -s /bin/bash appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Entrypoint que aplica migraciones (si están disponibles) y arranca la app
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
