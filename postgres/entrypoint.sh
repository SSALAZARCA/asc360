#!/bin/sh
set -e

# Si ya existe una base de datos, forzar trust auth en pg_hba.conf
if [ -f "/var/lib/postgresql/data/pg_hba.conf" ]; then
    echo "==> Forzando trust auth en pg_hba.conf existente..."
    cat > /var/lib/postgresql/data/pg_hba.conf << 'EOF'
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
host    all             all             all                     trust
EOF
fi

exec docker-entrypoint.sh "$@"
