# Usar una imagen base de Python (slim para que sea ligera)
FROM python:3.10-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar archivo de requisitos e instalar dependencias
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación al contenedor
COPY . .

# Exponer el puerto en el que Flask correrá (5000)
EXPOSE 5000

# Comando por defecto: ejecutar la app Flask
CMD ["python", "app.py"]
