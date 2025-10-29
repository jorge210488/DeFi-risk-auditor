FROM python:3.10-slim
WORKDIR /app
ENV PYTHONPATH=/app

# Crear usuario no-root
RUN useradd -m -u 1000 -s /bin/bash appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código y entrypoint
COPY . .
COPY entrypoint.sh /app/entrypoint.sh

# Aún como root: dar permisos y propiedad
RUN chmod +x /app/entrypoint.sh && chown -R appuser:appuser /app

# Cambiar a usuario no-root
USER appuser

EXPOSE 5000
CMD ["/app/entrypoint.sh"]
