"""add proveedor role

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-06

PostgreSQL requiere que ALTER TYPE ADD VALUE sea commiteado antes de poder
usar el nuevo valor en la misma sesión. Se usa autocommit_block.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE role ADD VALUE IF NOT EXISTS 'proveedor'"))


def downgrade():
    # PostgreSQL no permite remover valores de enum sin recrear el tipo.
    # 'proveedor' permanece en el enum pero queda sin uso tras el downgrade.
    pass
