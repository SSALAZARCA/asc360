"""venta_detalle: una fila por linea del archivo VENTAS

Revision ID: b8e2d4a1c735
Revises: a3f7c1d9e642
Create Date: 2026-09-30 23:00:00.000000

Detalle por linea de la carga VENTAS (vendedor, valor bruto, descuento,
cliente de la factura y nro de documento). Alimenta los indicadores del
tablero de asesores; el motor de pedidos NUNCA lo lee, sigue leyendo solo
`venta_mensual`.

Estrictamente ADITIVA: una tabla nueva con sus indices, sin tocar ninguna
tabla existente. `carga_id` queda en cada fila para que todo lector filtre
las cargas ANULADAS (anular una carga NO borra el detalle).

Downgrade: borra la tabla (se pierde el detalle por linea; `venta_mensual`
queda intacta).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8e2d4a1c735'
down_revision: Union[str, None] = 'a3f7c1d9e642'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'venta_detalle',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('anio', sa.Integer(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('origen', sa.String(length=12), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('vendedor', sa.String(length=255), nullable=False),
        sa.Column('vendedor_norm', sa.String(length=255), nullable=False),
        sa.Column('valor_bruto', sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column('valor_descuentos', sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column('cliente_factura', sa.String(length=255), nullable=False),
        sa.Column('nro_documento', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_venta_detalle_sucursal_id_fecha', 'venta_detalle',
        ['sucursal_id', 'fecha'], unique=False,
    )
    op.create_index(
        'ix_venta_detalle_vendedor_norm_fecha', 'venta_detalle',
        ['vendedor_norm', 'fecha'], unique=False,
    )
    op.create_index('ix_venta_detalle_carga_id', 'venta_detalle', ['carga_id'], unique=False)
    op.create_index(
        'ix_venta_detalle_sucursal_id_nro_documento', 'venta_detalle',
        ['sucursal_id', 'nro_documento'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_venta_detalle_sucursal_id_nro_documento', table_name='venta_detalle')
    op.drop_index('ix_venta_detalle_carga_id', table_name='venta_detalle')
    op.drop_index('ix_venta_detalle_vendedor_norm_fecha', table_name='venta_detalle')
    op.drop_index('ix_venta_detalle_sucursal_id_fecha', table_name='venta_detalle')
    op.drop_table('venta_detalle')
