#!/bin/bash
set -e

echo "==> DATABASE_URL: $DATABASE_URL"
echo "==> Corriendo migraciones de Alembic..."
alembic upgrade head

echo "==> Creando superadmin (si no existe)..."
python scripts/create_superadmin.py || echo "Superadmin ya existe o error no crítico, continuando..."

echo "==> Iniciando servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
