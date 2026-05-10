#!/bin/sh
set -e

PGDATA=/var/lib/postgresql/data

if [ -f "$PGDATA/PG_VERSION" ]; then
    echo "==> Base de datos existente detectada. Reseteando credenciales..."

    chown -R postgres:postgres "$PGDATA" 2>/dev/null || true

    # Garantiza que local use trust antes de arrancar, para que psql del entrypoint pueda conectar
    if [ -f "$PGDATA/pg_hba.conf" ]; then
        sed -i 's/^local.*/local   all             all                                     trust/' "$PGDATA/pg_hba.conf"
    fi

    su-exec postgres pg_ctl -D "$PGDATA" -o "-c listen_addresses=''" -w start

    su-exec postgres psql -U "${POSTGRES_USER:-umadmin}" postgres \
        -c "ALTER USER \"${POSTGRES_USER:-umadmin}\" WITH PASSWORD '${POSTGRES_PASSWORD}';"

    cat > "$PGDATA/pg_hba.conf" << 'PGEOF'
local   all             all                                     trust
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256
host    all             all             all                     scram-sha-256
PGEOF

    su-exec postgres psql -U "${POSTGRES_USER:-umadmin}" postgres -c "SELECT pg_reload_conf();"

    su-exec postgres pg_ctl -D "$PGDATA" -w stop

    echo "==> Credenciales reseteadas exitosamente."
    echo "==> pg_hba.conf actual:"
    cat "$PGDATA/pg_hba.conf"
fi

exec docker-entrypoint.sh "$@"
