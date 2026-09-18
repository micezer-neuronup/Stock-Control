# -----------------------------
# Base image: Python 3.11-slim
# -----------------------------
FROM python:3.11-slim

# -----------------------------
# Directorio de trabajo
# -----------------------------
WORKDIR /app

# -----------------------------
# Instalar dependencias del sistema necesarias
# -----------------------------
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------
# Copiar requirements.txt e instalar dependencias Python
# -----------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------
# Copiar el código de la aplicación
# -----------------------------
COPY . .

# -----------------------------
# Exponer el puerto 5000 (Flask)
# -----------------------------
EXPOSE 5000

# -----------------------------
# Comando por defecto para arrancar Flask
# -----------------------------
CMD ["python", "app.py"]