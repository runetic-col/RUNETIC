FROM python:3.11-slim

WORKDIR /app

# Copiar requirements
COPY backend/requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del backend
COPY backend/ .

# Exponer puerto
EXPOSE 8000

# Health check para verificar que el servicio esté activo
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/products', timeout=5)" || exit 1

# Ejecutar servidor
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
