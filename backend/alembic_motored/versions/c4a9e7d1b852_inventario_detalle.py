"""inventario_detalle: una fila por linea (bodega) del archivo INVENTARIO

Revision ID: c4a9e7d1b852
Revises: b8e2d4a1c735
Create Date: 2026-10-01 12:00:00.000000

Detalle por bodega de la carga INVENTARIO (codigo de bodega crudo, existencia
y costo promedio unitario). Alimenta el costo por referencia del tablero de
asesores; el motor de pedidos NUNCA lo lee, sigue leyendo solo
`inventario_snapshot` (que no cambia).

Estrictamente ADITIVA: una tabla nueva con sus indices, sin tocar ninguna
tabla existente. `carga_id` queda en cada fila para que todo lector filtre
las cargas ANULADAS (anular una carga NO borra el detalle). La purga de
retencion la borra junto con el snapshot.

Downgrade: borra la tabla (se pierde el detalle por bodega y el costo;
`inventario_snapshot` queda intacta).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4a9e7d1b852'
down_revision: Union[str, None] = 'b8e2d4a1c735'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'inventario_detalle',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('fecha_corte', sa.Date(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('bodega', sa.String(length=20), nullable=False),
        sa.Column('existencia', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('costo_unitario', sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_inventario_detalle_fecha_corte_sucursal_id', 'inventario_detalle',
        ['fecha_corte', 'sucursal_id'], unique=False,
    )
    op.create_index(
        'ix_inventario_detalle_referencia_id_fecha_corte', 'inventario_detalle',
        ['referencia_id', 'fecha_corte'], unique=False,
    )
    op.create_index(
        'ix_inventario_detalle_carga_id', 'inventario_detalle', ['carga_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_inventario_detalle_carga_id', table_name='inventario_detalle')
    op.drop_index('ix_inventario_detalle_referencia_id_fecha_corte', table_name='inventario_detalle')
    op.drop_index('ix_inventario_detalle_fecha_corte_sucursal_id', table_name='inventario_detalle')
    op.drop_table('inventario_detalle')
