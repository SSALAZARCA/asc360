#!/bin/bash
set -e

# Never print DATABASE_URL itself: it carries the DB password into deploy logs.
python - <<'PY' || echo "==> Base de datos: (no se pudo leer DATABASE_URL)"
import os
from urllib.parse import urlsplit

u = urlsplit(os.environ.get("DATABASE_URL", ""))
print(f"==> Base de datos: host={u.hostname or '?'} db={u.path.lstrip('/') or '?'}")
PY
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
