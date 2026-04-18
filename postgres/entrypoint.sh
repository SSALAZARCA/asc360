#!/bin/sh
set -e

PGDATA=/var/lib/postgresql/data

if [ -f "$PGDATA/PG_VERSION" ]; then
    echo "==> Base de datos existente detectada. Reseteando credenciales..."

    chown -R postgres:postgres "$PGDATA" 2>/dev/null || true

    su-exec postgres pg_ctl -D "$PGDATA" -o "-c listen_addresses=''" -w start

    su-exec postgres psql -U "${POSTGRES_USER:-umadmin}" postgres \
        -c "ALTER USER \"${POSTGRES_USER:-umadmin}\" WITH PASSWORD '${POSTGRES_PASSWORD:-UmAdmin2024Secure}';"

    cat > "$PGDATA/pg_hba.conf" << 'PGEOF'
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
host    all             all             all                     trust
PGEOF

    su-exec postgres psql -U "${POSTGRES_USER:-umadmin}" postgres -c "SELECT pg_reload_conf();"

    su-exec postgres pg_ctl -D "$PGDATA" -w stop

    echo "==> Credenciales reseteadas exitosamente."
fi

exec docker-entrypoint.sh "$@"
