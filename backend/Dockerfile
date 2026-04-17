# ==== STAGE 1: Base de dependencias del SO ====
FROM python:3.11-slim AS builder-base
# Dependencias del sistema (WeasyPrint, PostgreSQL client, compiladores)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    python3-cffi \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ==== STAGE 2: Construcción e instalación de paquetes ====
FROM builder-base AS deps
WORKDIR /build
COPY requirements.txt .
# Instalamos en un directorio local para copiar al final
RUN pip install --user --no-cache-dir -r requirements.txt

# ==== STAGE 3: Entorno de Producción Hardened ====
FROM builder-base AS runtime

# 1. Crear usuario no root (Security hardening)
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1001 appuser

WORKDIR /app

# 2. Copiar dependencias de Python del builder
COPY --from=deps --chown=appuser:appgroup /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# 3. Copiar el código fuente
COPY --chown=appuser:appgroup . .

# 4. Cambiar a usuario sin privilegios
USER 1001

EXPOSE 8000

# 5. Healthcheck (Performance & Resource Management)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando de ejecución
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
