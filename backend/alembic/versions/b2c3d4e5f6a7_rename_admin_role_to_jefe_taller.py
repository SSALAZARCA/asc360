"""rename admin role to jefe_taller

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-06

PostgreSQL requiere que ALTER TYPE ADD VALUE sea commiteado antes de poder
usar el nuevo valor en la misma sesión. Se usan dos bloques separados.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Bloque 1: ADD VALUE fuera de transacción (requiere autocommit en PG)
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE role ADD VALUE IF NOT EXISTS 'jefe_taller'"))

    # Bloque 2: migrar filas existentes (nueva transacción, valor ya commiteado)
    op.execute(sa.text("UPDATE users SET role = 'jefe_taller' WHERE role = 'admin'"))


def downgrade():
    op.execute(sa.text("UPDATE users SET role = 'admin' WHERE role = 'jefe_taller'"))
    # PostgreSQL no permite remover valores de un enum sin recrear el tipo.
    # 'jefe_taller' permanece en el enum pero queda sin uso tras el downgrade.
