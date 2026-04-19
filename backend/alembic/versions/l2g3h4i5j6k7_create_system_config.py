"""create system_config table

Revision ID: l2g3h4i5j6k7
Revises: k1f2a3b4c5d6
Create Date: 2026-04-19

Tabla global de configuración del sistema (logo de marca, etc.).
No está asociada a ningún taller específico.
"""
from alembic import op
import sqlalchemy as sa

revision = 'l2g3h4i5j6k7'
down_revision = 'k1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'system_config',
        sa.Column('key', sa.String(100), primary_key=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('system_config')
