#!/bin/bash
set -e

echo "==> DATABASE_URL: $DATABASE_URL"
echo "==> Corriendo migraciones de Alembic..."
alembic upgrade head

# Same source the app uses (env vars or the .env file read by app.config).
if python -c "from app.config import settings; raise SystemExit(0 if settings.MOTORED_DATABASE_URL else 1)"; then
    echo "==> Corriendo migraciones de Motored..."
    alembic -c alembic_motored.ini upgrade head || echo "==> ERROR: migraciones de Motored fallaron; el servidor arranca igual (revisar logs arriba)"
fi

echo "==> Creando superadmin (si no existe)..."
python scripts/create_superadmin.py || echo "Superadmin ya existe o error no crítico, continuando..."

echo "==> Iniciando servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
