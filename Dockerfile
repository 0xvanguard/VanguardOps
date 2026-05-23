FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema requeridas para PostgreSQL y compilación
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Exponer el puerto de la API
EXPOSE 8000
