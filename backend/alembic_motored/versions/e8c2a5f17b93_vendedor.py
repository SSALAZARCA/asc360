"""vendedor: maestro de vendedores

Revision ID: e8c2a5f17b93
Revises: d3b7f19a4c26
Create Date: 2026-10-01 16:00:00.000000

Maestro de vendedores del tablero de asesores: nombre del ERP, su clave
normalizada (la misma de `venta_detalle.vendedor_norm`), cargo, sucursal,
cedula y el Usuario enlazado a mano. El motor de pedidos NUNCA lo lee.

Estrictamente ADITIVA: una tabla nueva con sus indices, sin tocar ninguna
existente.

Downgrade: borra la tabla (se pierde el maestro y los enlaces a usuarios; se
recupera re-subiendo el Excel y re-enlazando a mano).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e8c2a5f17b93'
down_revision: Union[str, None] = 'd3b7f19a4c26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'vendedor',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('nombre', sa.String(length=255), nullable=False),
        sa.Column('nombre_norm', sa.String(length=255), nullable=False),
        sa.Column('cargo', sa.String(length=80), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=True),
        sa.Column('cedula', sa.String(length=20), nullable=True),
        sa.Column('usuario_id', sa.UUID(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_vendedor_nombre_norm', 'vendedor', ['nombre_norm'], unique=True)
    op.create_index('ix_vendedor_cargo', 'vendedor', ['cargo'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_vendedor_cargo', table_name='vendedor')
    op.drop_index('uq_vendedor_nombre_norm', table_name='vendedor')
    op.drop_table('vendedor')
