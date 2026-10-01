"""cliente_tecnired: lista de NIT de clientes Tecnired

Revision ID: d3b7f19a4c26
Revises: c4a9e7d1b852
Create Date: 2026-10-01 15:00:00.000000

Lista de clientes Tecnired que alimenta el tablero de asesores. Cada carga
desde Maestros REEMPLAZA la lista completa. El motor de pedidos NUNCA la lee.

Estrictamente ADITIVA: una tabla nueva, sin tocar ninguna existente.

Downgrade: borra la tabla (se pierde la lista cargada; se recupera re-subiendo
el Excel).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3b7f19a4c26'
down_revision: Union[str, None] = 'c4a9e7d1b852'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cliente_tecnired',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('nit', sa.String(length=30), nullable=False),
        sa.Column('razon_social', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nit'),
    )


def downgrade() -> None:
    op.drop_table('cliente_tecnired')
